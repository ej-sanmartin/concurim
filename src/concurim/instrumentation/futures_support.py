"""What happens to a ``Future`` after it leaves an executor.

``watch_future`` is called by the traced executors for each submission:

* a **cancellation** (``Future.cancel()`` on a task that had not started)
  becomes ``executor.task.cancelled``, attributed to the thread that
  cancelled it;
* each **done-callback** the program adds runs through a wrapper that records
  ``executor.callback`` first. It runs on the thread that completes (or
  cancels) the future, which is usually a pool worker, not the caller.

``traced_as_completed`` replaces ``concurrent.futures.as_completed`` while
recording and records ``executor.collected`` for each task it hands back, in
the order it hands them back (completion order, not submission order).
"""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)
mark_internal(concurrent.futures._base.__file__)

# Bound once: the function is replaced while auto-instrumenting.
_real_as_completed = concurrent.futures.as_completed


def _name_of(fn: Any) -> str:
    return str(getattr(fn, "__qualname__", None) or type(fn).__name__)[:80]


def _outcome(done: Any) -> str:
    if done.cancelled():
        return "cancelled"
    return "failed" if done.exception() is not None else "finished"


def watch_future(
    rec: Recorder,
    future: Any,
    *,
    rid: str,
    oid: str,
    op: str,
    name: str,
    suppress: Callable[[], bool] = lambda: False,
    on_cancel: Callable[[], object] = lambda: None,
) -> None:
    """Record the cancellation and callbacks of one submitted task.

    Args:
        rec: The active recorder.
        future: The ``Future`` returned by the executor's ``submit``.
        rid: The executor's resource id.
        oid: The task's object id.
        op: The task's operation id.
        name: The task's display name.
        suppress: Return True while the executor is dropping every pending
            task itself (``shutdown(cancel_futures=True)``), which its own
            event already describes.
        on_cancel: Called when the task is cancelled (cleanup hook).
    """
    future._cz_task = (rid, oid, op, name)

    def cancelled(done: Any) -> None:
        if not done.cancelled():
            return
        on_cancel()
        if not suppress():
            rec.emit(
                E.EXECUTOR_TASK_CANCELLED,
                resource_id=rid,
                object_id=oid,
                operation_id=op,
                source=rec.capture_source(),
                metadata={"name": name},
            )

    add = future.add_done_callback
    add(cancelled)

    def add_done_callback(fn: Callable[[Any], Any]) -> None:
        def run(done: Any) -> Any:
            active = active_recorder()
            if active is rec:
                rec.emit(
                    E.EXECUTOR_CALLBACK,
                    resource_id=rid,
                    object_id=oid,
                    source=rec.source_of_callable(fn),
                    metadata={
                        "callback": _name_of(fn),
                        "outcome": _outcome(done),
                    },
                )
            return fn(done)

        add(run)

    future.add_done_callback = add_done_callback


def _observe(rec: Recorder, futures: Iterator[Any]) -> Iterator[Any]:
    order = 0
    for future in futures:
        info = getattr(future, "_cz_task", None)
        if info is not None:
            rid, oid, _, name = info
            order += 1
            rec.emit(
                E.EXECUTOR_COLLECTED,
                resource_id=rid,
                object_id=oid,
                source=rec.capture_source(),
                metadata={"name": name, "order": order, "via": "as_completed"},
            )
        yield future


def traced_as_completed(
    fs: Iterable[Any], timeout: float | None = None
) -> Iterator[Any]:
    """``concurrent.futures.as_completed``, recording each hand-back."""
    rec = active_recorder()
    futures = _real_as_completed(fs, timeout)
    return futures if rec is None else _observe(rec, futures)
