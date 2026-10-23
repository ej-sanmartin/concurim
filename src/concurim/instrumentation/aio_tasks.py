"""asyncio task instrumentation: which task the event loop runs, and when.

Two reversible patches (applied by ``auto_instrument("asyncio")``):

* ``BaseEventLoop.create_task`` records each task's creation.
* ``Handle._run`` (every loop callback) notices callbacks that step a task
  and records ``task.step.started`` / ``task.step.ended`` around them, and
  attributes any event emitted inside the step to that task.

Tasks created eagerly (``eager_task_factory``) run their first step inside
``create_task`` and are only seen from their second step on. Loops that do
not use ``asyncio.events.Handle`` (for example uvloop) are not observed.
"""

from __future__ import annotations

import asyncio
import asyncio.base_events
import asyncio.events
import asyncio.locks
import asyncio.queues
import asyncio.runners
import asyncio.taskgroups
import asyncio.tasks
import weakref
from collections.abc import Callable
from typing import Any

from concurim.recorder.collector import INTERNAL_FILES, Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

for _module in (
    asyncio.base_events,
    asyncio.events,
    asyncio.locks,
    asyncio.queues,
    asyncio.runners,
    asyncio.taskgroups,
    asyncio.tasks,
):
    mark_internal(_module.__file__)
mark_internal(__file__)

# task -> (recorder, logical id or None). Weak, so finished tasks do not leak.
_IDS: weakref.WeakKeyDictionary[Any, tuple[Recorder, str | None]] = (
    weakref.WeakKeyDictionary()
)

# Tasks whose coroutine lives here are the loop's own housekeeping (closing
# async generators and the default executor), not the program's tasks.
_HOUSEKEEPING = {asyncio.base_events.__file__, asyncio.runners.__file__}


def _where(rec: Recorder, task: Any) -> Any:
    """Source of the deepest user frame the task is suspended in."""
    coro = task.get_coro()
    best = None
    while coro is not None:
        frame = getattr(coro, "cr_frame", None) or getattr(
            coro, "gi_frame", None
        )
        if frame is not None and frame.f_code.co_filename not in INTERNAL_FILES:
            best = frame
        coro = getattr(coro, "cr_await", None) or getattr(
            coro, "gi_yieldfrom", None
        )
    if best is None or not rec.config.capture_source_locations:
        return None
    return rec.source_of_frame(best)


def register(rec: Recorder, task: Any) -> str | None:
    """The task's logical id, recording ``task.created`` on first sight.

    Returns ``None`` for the event loop's own housekeeping tasks.
    """
    known = _IDS.get(task)
    if known is not None and known[0] is rec:
        return known[1]
    code = getattr(task.get_coro(), "cr_code", None)
    if code is not None and code.co_filename in _HOUSEKEEPING:
        _IDS[task] = (rec, None)
        return None
    tid = rec.ids.new_id("task")
    _IDS[task] = (rec, tid)
    rec.emit(
        E.TASK_CREATED,
        source=rec.capture_source(),
        metadata={"child": tid, "name": task.get_name()},
    )
    return tid


def _end_event(task: Any) -> tuple[str, dict[str, Any]]:
    if task.cancelled():
        return E.TASK_CANCELLED, {}
    # ``_exception`` avoids ``Task.exception()``, which would mark the
    # exception as retrieved and silence asyncio's own warning.
    error = getattr(task, "_exception", None)
    if error is not None:
        return E.TASK_FAILED, {"error": type(error).__name__}
    return E.TASK_FINISHED, {}


def _task_of(callback: Any) -> Any:
    owner = getattr(callback, "__self__", None)
    return owner if isinstance(owner, asyncio.Task) else None


def patched_run(original: Callable[..., Any]) -> Callable[..., Any]:
    """``Handle._run`` that brackets each task step with events."""

    def _run(self: Any) -> None:
        rec = active_recorder()
        task = _task_of(self._callback) if rec is not None else None
        if rec is None or task is None:
            return original(self)
        tid = register(rec, task)
        if tid is None:
            return original(self)
        rec.set_task(tid)
        try:
            rec.emit(E.TASK_STEP_STARTED, source=_where(rec, task))
            original(self)
        finally:
            done = task.done()
            rec.emit(
                E.TASK_STEP_ENDED,
                source=None if done else _where(rec, task),
                metadata={"done": done},
            )
            if done:
                kind, meta = _end_event(task)
                rec.emit(kind, metadata=meta)
            rec.set_task(None)
        return None

    return _run


def patched_create_task(original: Callable[..., Any]) -> Callable[..., Any]:
    """``BaseEventLoop.create_task`` that records the new task."""

    def create_task(self: Any, coro: Any, **kwargs: Any) -> Any:
        task = original(self, coro, **kwargs)
        rec = active_recorder()
        if rec is not None:
            register(rec, task)
        return task

    return create_task
