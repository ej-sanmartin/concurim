"""Instrumented ``concurrent.futures.ProcessPoolExecutor``.

The parent records ``submit`` and shutdown. Each worker process reports when
a task starts and ends (see ``mp_support``); a thread in the parent turns
those reports into events, attributed to a logical actor per worker
process.
"""

from __future__ import annotations

import concurrent.futures
import concurrent.futures.process
import contextlib
import functools
import multiprocessing
import multiprocessing.queues
from collections.abc import Callable
from typing import Any

from concurim.instrumentation.futures_support import watch_future
from concurim.instrumentation.mp_support import (
    child_call,
    child_init,
    describe_args,
)
from concurim.instrumentation.mp_tasks import TaskSink
from concurim.instrumentation.threads import PLUMBING_FILES
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder
from concurim.recorder.sampler import wanted

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
        self._cz_sink: TaskSink | None = None
        self._cz_closed = False
        self._cz_dropping = False
        rec = active_recorder()
        if rec is not None and self._cz_on:
            mp_context = mp_context or multiprocessing.get_context()
            self._cz_sink = TaskSink(rec, mp_context)
            sampling = (
                (rec.root, rec.config.sample_interval_ms / 1000)
                if wanted(rec.config)
                else None
            )
            initargs = (self._cz_sink.queue, initializer, initargs, sampling)
            initializer = child_init
        # The stub's overloads cannot express "initializer maybe ours".
        super().__init__(  # ty: ignore[no-matching-overload]
            max_workers,
            mp_context,
            initializer,
            initargs,
            max_tasks_per_child=max_tasks_per_child,
        )
        if self._cz_sink is not None and rec is not None:
            self._cz_rid(rec)
            self._cz_sink.start()

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
        sink = self._cz_sink
        rec = active_recorder() if sink is not None else None
        if rec is None or sink is None:
            return super().submit(fn, *args, **kwargs)
        rid = self._cz_rid(rec)
        oid, op = rec.new_object_id(), rec.new_operation_id()
        user_fn = _task_of(fn)
        name = str(
            getattr(user_fn, "__qualname__", None) or type(user_fn).__name__
        )[:80]
        sink.pending[op] = (rid, oid, name, rec.source_of_callable(user_fn))
        rec.emit(
            E.EXECUTOR_SUBMIT,
            resource_id=rid,
            object_id=oid,
            operation_id=op,
            source=rec.capture_source(),
            metadata={"name": name, **describe_args(args, kwargs)},
        )
        future = super().submit(child_call, op, fn, args, kwargs)
        watch_future(
            rec,
            future,
            rid=rid,
            oid=oid,
            op=op,
            name=name,
            suppress=lambda: self._cz_dropping,
            on_cancel=lambda: sink.pending.pop(op, None),
        )
        return future

    def shutdown(
        self, wait: bool = True, *, cancel_futures: bool = False
    ) -> None:
        """``ProcessPoolExecutor.shutdown``; the first call is recorded."""
        rec = active_recorder() if self._cz_sink is not None else None
        if rec is not None and not self._cz_closed:
            self._cz_closed = True
            self._cz_dropping = cancel_futures
            # Recording must never keep the pool from shutting down.
            with contextlib.suppress(Exception):
                rec.emit(
                    E.EXECUTOR_SHUTDOWN,
                    resource_id=self._cz_rid(rec),
                    source=rec.capture_source(),
                    metadata={"wait": wait, "cancel_futures": cancel_futures},
                )
        super().shutdown(wait, cancel_futures=cancel_futures)
        if wait and self._cz_sink is not None and rec is not None:
            self._cz_sink.close()  # all workers are gone: flush and stop
