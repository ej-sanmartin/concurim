"""Instrumented ``concurrent.futures.ThreadPoolExecutor``.

``submit`` records the submission; the wrapper that runs inside the worker
records when the task starts and how it ends. Everything else about the
executor (and its ``Future`` objects) is the standard library's.
"""

from __future__ import annotations

import concurrent.futures
import concurrent.futures.thread
import contextlib
from collections.abc import Callable
from typing import Any

from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)
mark_internal(concurrent.futures.thread.__file__)

# Bound once: the class may be replaced while auto-instrumenting.
_BasePool = concurrent.futures.ThreadPoolExecutor


def _call(
    rec: Recorder,
    rid: str,
    oid: str,
    op: str,
    name: str,
    fn: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Run ``fn`` in the worker, recording start and outcome."""
    rec.emit(
        E.EXECUTOR_TASK_STARTED,
        resource_id=rid,
        object_id=oid,
        operation_id=op,
        source=rec.source_of_callable(fn),
        metadata={"name": name},
    )
    try:
        result = fn(*args, **kwargs)
    except BaseException as error:
        rec.emit(
            E.EXECUTOR_TASK_FAILED,
            resource_id=rid,
            object_id=oid,
            operation_id=op,
            metadata={"name": name, "error": type(error).__name__},
        )
        raise
    rec.emit(
        E.EXECUTOR_TASK_FINISHED,
        resource_id=rid,
        object_id=oid,
        operation_id=op,
        metadata={"name": name},
    )
    return result


class TracedThreadPoolExecutor(_BasePool):
    """``ThreadPoolExecutor`` that records submissions and task runs.

    Takes the same arguments plus ``name`` (display name in the viewer).
    """

    _cz_on = True

    def __init__(
        self,
        max_workers: int | None = None,
        *args: Any,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(max_workers, *args, **kwargs)
        self._cz_name = name
        rec = active_recorder()
        if rec is not None and self._cz_on:
            self._cz_rid(rec)

    def _cz_rid(self, rec: Recorder) -> str:
        return rec.resource_id(
            self,
            "executor",
            self._cz_name,
            {"max_workers": self._max_workers},
        )

    def submit(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any):
        """``ThreadPoolExecutor.submit``, recording the task's journey."""
        rec = active_recorder() if self._cz_on else None
        if rec is None:
            return super().submit(fn, *args, **kwargs)
        rid = self._cz_rid(rec)
        oid, op = rec.new_object_id(), rec.new_operation_id()
        name = str(getattr(fn, "__qualname__", None) or type(fn).__name__)[:80]
        rec.emit(
            E.EXECUTOR_SUBMIT,
            resource_id=rid,
            object_id=oid,
            operation_id=op,
            source=rec.capture_source(),
            metadata={"name": name},
        )
        return super().submit(_call, rec, rid, oid, op, name, fn, args, kwargs)

    def shutdown(
        self, wait: bool = True, *, cancel_futures: bool = False
    ) -> None:
        """``ThreadPoolExecutor.shutdown``; the first call is recorded."""
        rec = active_recorder() if self._cz_on else None
        if rec is not None and not getattr(self, "_cz_closed", False):
            self._cz_closed = True
            # Recording must never keep the pool from shutting down.
            with contextlib.suppress(Exception):
                rec.emit(
                    E.EXECUTOR_SHUTDOWN,
                    resource_id=self._cz_rid(rec),
                    source=rec.capture_source(),
                    metadata={"wait": wait, "cancel_futures": cancel_futures},
                )
        super().shutdown(wait, cancel_futures=cancel_futures)
