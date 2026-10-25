"""Instrumented ``concurrent.futures.ProcessPoolExecutor``.

The parent records ``submit`` and shutdown. Each worker process reports when
a task starts and ends through a pipe it inherits at start-up; a thread in
the parent turns those reports into events, attributed to a logical actor per
worker process. No pickling of recorder state happens: only small tuples of
primitives cross the pipe.

Honest limits: events from workers are stamped when the parent *receives*
them (the worker's own clock reading is kept in ``child_ns``), and nothing
that happens inside a worker besides task start/end is observed.
"""

from __future__ import annotations

import concurrent.futures
import concurrent.futures.process
import contextlib
import functools
import multiprocessing
import multiprocessing.queues
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from concurim.instrumentation.threads import PLUMBING_FILES
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.events import Source
from concurim.recorder.lifecycle import active_recorder, forget_recorder
from concurim.recorder.sampler import LineSampler, wanted

mark_internal(__file__)
mark_internal(concurrent.futures.process.__file__)
PLUMBING_FILES.update(
    {
        __file__,
        concurrent.futures.process.__file__,
        multiprocessing.queues.__file__,
    }
)

# Bound once: the class may be replaced while auto-instrumenting.
_BasePool = concurrent.futures.ProcessPoolExecutor

# Set in each worker process by ``_child_init`` and ``_child_call``.
_CHILD_QUEUE: Any = None
_CURRENT_OP: str | None = None


def _child_init(
    queue: Any,
    init: Callable[..., Any] | None,
    args: Any,
    sampling: tuple[str, float] | None,
) -> None:
    """Runs first in every worker: remember the pipe, then the user's init.

    ``sampling`` is ``(source root, seconds between samples)`` or ``None``.
    """
    global _CHILD_QUEUE
    _CHILD_QUEUE = queue
    forget_recorder()  # a forked worker inherits the parent's recorder
    if sampling is not None:
        main = threading.get_ident()
        LineSampler(
            sampling[0],
            sampling[1],
            lambda ident: _CURRENT_OP if ident == main else None,
            lambda op, file, line, name: _report(
                "line", op, where=(file, line, name)
            ),
        ).start()
    if init is not None:
        init(*args)


def _report(
    kind: str,
    op: str,
    error: str | None = None,
    where: tuple[str, int, str] | None = None,
) -> None:
    """Send one report to the parent; never let it break the task."""
    queue = _CHILD_QUEUE
    if queue is None:
        return
    name = multiprocessing.current_process().name
    # Recording must never alter or break the program being recorded.
    with contextlib.suppress(Exception):
        queue.put(
            (kind, op, os.getpid(), name, time.perf_counter_ns(), error, where)
        )


def _child_call(
    op: str,
    fn: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Run ``fn`` in the worker, reporting start and outcome."""
    global _CURRENT_OP
    _report("started", op)
    _CURRENT_OP = op  # after "started", so no sample precedes it
    try:
        result = fn(*args, **kwargs)
    except BaseException as error:
        _CURRENT_OP = None
        _report("failed", op, type(error).__name__)
        raise
    _CURRENT_OP = None
    _report("finished", op)
    return result


def _task_of(fn: Callable[..., Any]) -> Callable[..., Any]:
    """The user's function behind ``Executor.map``'s chunking wrapper."""
    chunk = concurrent.futures.process._process_chunk  # noqa: SLF001
    if isinstance(fn, functools.partial) and fn.func is chunk and fn.args:
        return fn.args[0]
    return fn


class TracedProcessPoolExecutor(_BasePool):
    """``ProcessPoolExecutor`` that records submissions and worker task runs.

    Takes the same arguments plus ``name`` (display name in the viewer).
    Outside a recording it behaves exactly like the standard class.
    """

    _cz_on = True

    def __init__(
        self,
        max_workers: int | None = None,
        mp_context: Any = None,
        initializer: Callable[..., Any] | None = None,
        initargs: tuple[Any, ...] = (),
        *,
        max_tasks_per_child: int | None = None,
        name: str | None = None,
    ) -> None:
        self._cz_name = name
        self._cz_queue: Any = None
        self._cz_pending: dict[str, tuple[str, str, str, Source | None]] = {}
        self._cz_actors: list[str] = []
        self._cz_thread: threading.Thread | None = None
        self._cz_closed = False
        rec = active_recorder()
        if rec is not None and self._cz_on:
            mp_context = mp_context or multiprocessing.get_context()
            self._cz_queue = mp_context.SimpleQueue()
            sampling = (
                (rec.root, rec.config.sample_interval_ms / 1000)
                if wanted(rec.config)
                else None
            )
            initargs = (self._cz_queue, initializer, initargs, sampling)
            initializer = _child_init
        # The stub's overloads cannot express "initializer maybe ours".
        super().__init__(  # ty: ignore[no-matching-overload]
            max_workers,
            mp_context,
            initializer,
            initargs,
            max_tasks_per_child=max_tasks_per_child,
        )
        if self._cz_queue is not None and rec is not None:
            self._cz_rid(rec)
            self._cz_thread = threading.Thread(
                target=self._cz_drain, args=(rec,), daemon=True
            )
            self._cz_thread.start()

    def _cz_rid(self, rec: Recorder) -> str:
        return rec.resource_id(
            self,
            "executor",
            self._cz_name,
            {
                "max_workers": self._max_workers,  # ty: ignore[unresolved-attribute]
                "pool": "process",
            },
        )

    def submit(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any):
        """``ProcessPoolExecutor.submit``, recording the task's journey."""
        rec = active_recorder() if self._cz_queue is not None else None
        if rec is None:
            return super().submit(fn, *args, **kwargs)
        rid = self._cz_rid(rec)
        oid, op = rec.new_object_id(), rec.new_operation_id()
        user_fn = _task_of(fn)
        name = str(
            getattr(user_fn, "__qualname__", None) or type(user_fn).__name__
        )[:80]
        self._cz_pending[op] = (rid, oid, name, rec.source_of_callable(user_fn))
        rec.emit(
            E.EXECUTOR_SUBMIT,
            resource_id=rid,
            object_id=oid,
            operation_id=op,
            source=rec.capture_source(),
            metadata={"name": name},
        )
        return super().submit(_child_call, op, fn, args, kwargs)

    def shutdown(
        self, wait: bool = True, *, cancel_futures: bool = False
    ) -> None:
        """``ProcessPoolExecutor.shutdown``; the first call is recorded."""
        rec = active_recorder() if self._cz_queue is not None else None
        if rec is not None and not self._cz_closed:
            self._cz_closed = True
            rec.emit(
                E.EXECUTOR_SHUTDOWN,
                resource_id=self._cz_rid(rec),
                source=rec.capture_source(),
                metadata={"wait": wait, "cancel_futures": cancel_futures},
            )
        super().shutdown(wait, cancel_futures=cancel_futures)
        if wait and self._cz_thread is not None and rec is not None:
            self._cz_queue.put(None)  # all workers are gone: flush and stop
            self._cz_thread.join()
            for actor in self._cz_actors:
                rec.emit_as(actor, E.THREAD_FINISHED)

    def _cz_drain(self, rec: Recorder) -> None:
        """Turn worker reports into events until told to stop."""
        while (report := self._cz_queue.get()) is not None:
            kind, op, pid, pname, child_ns, error, where = report
            known = self._cz_pending.get(op)
            if known is None:
                continue
            rid, oid, name, src = known
            actor = rec.remote_actor(str(pid), pname, pid)
            if actor not in self._cz_actors:
                self._cz_actors.append(actor)
            if kind == "line":
                if where is not None:
                    file, line, function = where
                    rec.emit_as(
                        actor,
                        E.CODE_SAMPLED,
                        source=Source(rec.display_path(file), line, function),
                    )
                continue
            meta: dict[str, Any] = {
                "name": name,
                "worker_pid": pid,
                "child_ns": child_ns,
            }
            if kind == "started":
                etype = E.EXECUTOR_TASK_STARTED
            else:
                del self._cz_pending[op]
                src = None
                if kind == "failed":
                    meta["error"] = error or "Exception"
                    etype = E.EXECUTOR_TASK_FAILED
                else:
                    etype = E.EXECUTOR_TASK_FINISHED
            rec.emit_as(
                actor,
                etype,
                resource_id=rid,
                object_id=oid,
                operation_id=op,
                source=src,
                metadata=meta,
            )
