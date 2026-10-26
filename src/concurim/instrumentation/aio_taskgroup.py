"""Instrumented ``asyncio.TaskGroup``.

Records which tasks were created through the group and when the ``async
with`` block reached its end and started waiting for them. The tasks'
own lives (steps, failure, cancellation) come from ``aio_tasks``; if one
child fails, the group cancels the rest and those cancellations appear as
ordinary ``task.cancelled`` events. Needs the asyncio instrumentation level
(or the child tasks are not observed).
"""

from __future__ import annotations

import asyncio
from typing import Any

from concurim.instrumentation.aio_tasks import register
from concurim.instrumentation.auto_support import creation_name
from concurim.instrumentation.queue_support import _Op
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)

# Bound once: ``asyncio.TaskGroup`` may be replaced while patched.
_BaseTaskGroup = asyncio.TaskGroup


class TracedTaskGroup(_BaseTaskGroup):
    """``asyncio.TaskGroup`` that records its tasks and its exit.

    Args:
        name: Display name in the viewer.
    """

    def __init__(self, *, name: str | None = None) -> None:
        super().__init__()
        self._cz_name = name

    def _cz_rid(self, rec: Recorder) -> str:
        return rec.resource_id(self, "taskgroup", self._cz_name, {})

    async def __aenter__(self) -> TracedTaskGroup:
        rec = active_recorder()
        if rec is not None:
            self._cz_rid(rec)
        await super().__aenter__()
        return self

    def create_task(self, coro: Any, **kwargs: Any) -> asyncio.Task:
        """``TaskGroup.create_task``, recording the new member."""
        task = super().create_task(coro, **kwargs)
        rec = active_recorder()
        if rec is not None:
            child = register(rec, task)
            rec.emit(
                E.TASKGROUP_TASK_ADDED,
                resource_id=self._cz_rid(rec),
                source=rec.capture_source(),
                metadata={"child": child or "", "name": task.get_name()},
            )
        return task

    async def __aexit__(self, et: Any, exc: Any, tb: Any) -> bool | None:  # ty: ignore[invalid-method-override]
        rec = active_recorder()
        if rec is None:
            return await super().__aexit__(et, exc, tb)
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        op.emit(
            E.TASKGROUP_EXIT_STARTED,
            running=sum(not t.done() for t in self._tasks),
            body_error=type(exc).__name__ if exc is not None else None,
        )
        try:
            suppressed = await super().__aexit__(et, exc, tb)
        except BaseException as error:
            op.emit(E.TASKGROUP_EXIT_COMPLETED, error=type(error).__name__)
            raise
        op.emit(E.TASKGROUP_EXIT_COMPLETED, error=None)
        return suppressed


class AutoTaskGroup(TracedTaskGroup):
    """``TracedTaskGroup`` named after the line that created it."""

    def __init__(self) -> None:
        super().__init__(name=creation_name("TaskGroup"))
