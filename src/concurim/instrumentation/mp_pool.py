"""Instrumented ``multiprocessing.Pool``.

Every item of ``map``/``starmap``/``imap`` and every ``apply`` call is one
task, shown like an executor task: submitted by the caller, started and
finished by a worker process. Pool-internal chunking is not shown.
``AsyncResult.get()`` and callbacks are not observed.
"""

from __future__ import annotations

import multiprocessing
import multiprocessing.pool
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from concurim.instrumentation.mp_support import (
    child_call,
    child_init,
    describe_args,
)
from concurim.instrumentation.mp_tasks import TaskSink
from concurim.instrumentation.threads import PLUMBING_FILES
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.events import Source
from concurim.recorder.lifecycle import active_recorder
from concurim.recorder.sampler import wanted

mark_internal(__file__)
mark_internal(multiprocessing.pool.__file__)
PLUMBING_FILES.update({__file__, multiprocessing.pool.__file__})

# Bound once: ``multiprocessing.pool.Pool`` may be replaced while patched.
_BasePool = multiprocessing.pool.Pool


class _MapCall:
    """Runs ``func(item)`` for an ``(operation id, item)`` pair."""

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func

    def __call__(self, pair: tuple[str, Any]) -> Any:
        op, item = pair
        return child_call(op, self.func, (item,), {})


class _StarCall:
    """Runs ``func(*args)`` for an ``(operation id, args)`` pair."""

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func

    def __call__(self, op: str, args: Iterable[Any]) -> Any:
        return child_call(op, self.func, tuple(args), {})


class TracedPool(_BasePool):
    """``multiprocessing.Pool`` that records tasks and worker processes.

    Same arguments as ``multiprocessing.pool.Pool`` plus ``name`` (display
    name in the viewer). Outside a recording it behaves exactly like the
    standard class.
    """

    _cz_on = True

    def __init__(
        self,
        processes: int | None = None,
        initializer: Callable[..., Any] | None = None,
        initargs: tuple[Any, ...] = (),
        maxtasksperchild: int | None = None,
        context: Any = None,
        *,
        name: str | None = None,
    ) -> None:
        self._cz_name = name
        self._cz_sink: TaskSink | None = None
        self._cz_closed = False
        rec = active_recorder()
        if rec is not None and self._cz_on:
            context = context or multiprocessing.get_context()
            self._cz_sink = TaskSink(rec, context)
            sampling = (
                (rec.root, rec.config.sample_interval_ms / 1000)
                if wanted(rec.config)
                else None
            )
            initargs = (self._cz_sink.queue, initializer, initargs, sampling)
            initializer = child_init
        super().__init__(
            processes, initializer, initargs, maxtasksperchild, context
        )
        if self._cz_sink is not None and rec is not None:
            self._cz_rid(rec)
            self._cz_sink.start()

    def _cz_rid(self, rec: Recorder) -> str:
        return rec.resource_id(
            self,
            "executor",
            self._cz_name,
            {"max_workers": self._processes, "pool": "process"},  # ty: ignore[unresolved-attribute]
        )

    def _cz_submit(
        self,
        rec: Recorder,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        source: Source | None,
        actor: str | None = None,
    ) -> str:
        """Record one task as submitted; returns its operation id."""
        assert self._cz_sink is not None
        rid = self._cz_rid(rec)
        oid, op = rec.new_object_id(), rec.new_operation_id()
        name = str(getattr(func, "__qualname__", None) or type(func).__name__)
        self._cz_sink.pending[op] = (
            rid,
            oid,
            name[:80],
            rec.source_of_callable(func),
        )
        fields: dict[str, Any] = {
            "resource_id": rid,
            "object_id": oid,
            "operation_id": op,
            "source": source,
            "metadata": {"name": name[:80], **describe_args(args, kwargs)},
        }
        if actor is None:
            rec.emit(E.EXECUTOR_SUBMIT, **fields)
        else:
            rec.emit_as(actor, E.EXECUTOR_SUBMIT, **fields)
        return op

    def _cz_active(self) -> Recorder | None:
        return active_recorder() if self._cz_sink is not None else None

    def apply_async(  # ty: ignore[invalid-method-override]
        self,
        func: Callable[..., Any],
        args: Iterable[Any] = (),
        kwds: dict[str, Any] | None = None,
        callback: Callable[[Any], object] | None = None,
        error_callback: Callable[[BaseException], object] | None = None,
    ) -> Any:
        """``Pool.apply_async`` (and ``apply``), recording one task."""
        kwds = {} if kwds is None else kwds
        rec = self._cz_active()
        if rec is None:
            return super().apply_async(
                func, args, kwds, callback, error_callback
            )
        args = tuple(args)
        op = self._cz_submit(rec, func, args, kwds, rec.capture_source())
        return super().apply_async(
            child_call, (op, func, args, kwds), {}, callback, error_callback
        )

    def _map_async(  # noqa: PLR0913 - mirrors the standard signature
        self,
        func: Callable[..., Any],
        iterable: Iterable[Any],
        mapper: Callable[..., Any],
        chunksize: int | None = None,
        callback: Callable[[Any], object] | None = None,
        error_callback: Callable[[BaseException], object] | None = None,
    ) -> Any:
        """Common path of ``map``, ``starmap`` and their ``_async`` forms."""
        rec = self._cz_active()
        star = mapper is multiprocessing.pool.starmapstar  # ty: ignore[unresolved-attribute]
        if rec is None or not (star or mapper is multiprocessing.pool.mapstar):  # ty: ignore[unresolved-attribute]
            return super()._map_async(  # ty: ignore[unresolved-attribute]
                func, iterable, mapper, chunksize, callback, error_callback
            )
        if not hasattr(iterable, "__len__"):
            iterable = list(iterable)
        source = rec.capture_source()
        pairs = [
            (
                self._cz_submit(
                    rec,
                    func,
                    tuple(item) if star else (item,),
                    {},
                    source,
                ),
                item,
            )
            for item in iterable
        ]
        return super()._map_async(  # ty: ignore[unresolved-attribute]
            _StarCall(func) if star else _MapCall(func),
            pairs,
            mapper,
            chunksize,
            callback,
            error_callback,
        )

    def _cz_lazy(
        self, func: Callable[..., Any], iterable: Iterable[Any]
    ) -> tuple[Callable[..., Any], Iterable[Any]]:
        """Wrap ``func`` and ``iterable`` for ``imap``; tasks are submitted
        as the pool pulls items, on behalf of the calling thread."""
        rec = self._cz_active()
        if rec is None:
            return func, iterable
        actor, source = rec.current_actor(), rec.capture_source()

        def announce() -> Iterator[tuple[str, Any]]:
            for item in iterable:
                op = self._cz_submit(rec, func, (item,), {}, source, actor)
                yield op, item

        return _MapCall(func), announce()

    def imap(  # ty: ignore[invalid-method-override]
        self,
        func: Callable[..., Any],
        iterable: Iterable[Any],
        chunksize: int = 1,
    ) -> Any:
        """``Pool.imap``; each item is one recorded task."""
        func, iterable = self._cz_lazy(func, iterable)
        return super().imap(func, iterable, chunksize)

    def imap_unordered(  # ty: ignore[invalid-method-override]
        self,
        func: Callable[..., Any],
        iterable: Iterable[Any],
        chunksize: int = 1,
    ) -> Any:
        """``Pool.imap_unordered``; each item is one recorded task."""
        func, iterable = self._cz_lazy(func, iterable)
        return super().imap_unordered(func, iterable, chunksize)

    def _cz_shutdown(self, graceful: bool) -> None:
        """Record the first ``close()`` or ``terminate()`` call."""
        rec = self._cz_active()
        if rec is None or self._cz_closed or self._cz_sink is None:
            return
        self._cz_closed = True
        if not graceful:
            # Reports may still be in the pipe; tasks that finished are not
            # dropped (Windows reads them noticeably later).
            self._cz_sink.sync()
        dropped = not graceful and bool(self._cz_sink.pending)
        rec.emit(
            E.EXECUTOR_SHUTDOWN,
            resource_id=self._cz_rid(rec),
            source=rec.capture_source(),
            metadata={"wait": graceful, "cancel_futures": dropped},
        )

    def close(self) -> None:
        """``Pool.close``: no new tasks; queued ones still run."""
        self._cz_shutdown(True)
        super().close()

    def terminate(self) -> None:
        """``Pool.terminate`` (also what ``with Pool()`` does on exit)."""
        self._cz_shutdown(False)
        super().terminate()
        if self._cz_sink is not None:
            self._cz_sink.close()

    def join(self) -> None:
        """``Pool.join``; once the workers are gone, flush their reports."""
        super().join()
        if self._cz_sink is not None:
            self._cz_sink.close()
