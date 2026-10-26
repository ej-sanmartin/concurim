"""Instrumented ``asyncio.Event`` and ``asyncio.Condition``.

They emit the same events as the threaded versions; the actor is the asyncio
task running the call (see ``aio_tasks``). A task that waits is *suspended*
while the other tasks keep running. As with threads, a notified task must
re-acquire the condition's lock before it continues, and the wake-up order is
not recorded.
"""

from __future__ import annotations

import asyncio
from typing import Any

from concurim.instrumentation.aio_primitives import TracedAsyncLock, _why
from concurim.instrumentation.queue_support import _Op
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)

# Bound once: the ``asyncio`` attributes may be replaced while patched.
_BaseEvent = asyncio.Event
_BaseCondition = asyncio.Condition


class TracedAsyncEvent(_BaseEvent):
    """``asyncio.Event`` that records set, clear and waits.

    Args:
        name: Display name in the viewer.
    """

    def __init__(self, *, name: str | None = None) -> None:
        super().__init__()
        self._cz_name = name
        rec = active_recorder()
        if rec is not None:
            self._cz_rid(rec)

    def _cz_rid(self, rec: Recorder) -> str:
        return rec.resource_id(
            self, "event", self._cz_name, {"is_set": self.is_set()}
        )

    def _cz_emit(self, rec: Recorder, kind: str, **meta: Any) -> None:
        rec.emit(
            kind,
            resource_id=self._cz_rid(rec),
            source=rec.capture_source(),
            metadata=meta,
        )

    def set(self) -> None:
        """``Event.set``; recorded before the flag flips."""
        rec = active_recorder()
        if rec is not None:
            self._cz_emit(rec, E.EVENT_SET, already_set=self.is_set())
        super().set()

    def clear(self) -> None:
        """``Event.clear``."""
        rec = active_recorder()
        if rec is not None:
            self._cz_emit(rec, E.EVENT_CLEARED, was_set=self.is_set())
        super().clear()

    async def wait(self) -> bool:  # ty: ignore[invalid-method-override]
        """``Event.wait``; an unset event suspends the calling task."""
        rec = active_recorder()
        if rec is None:
            return await super().wait()
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        op.emit(E.EVENT_WAIT_STARTED)
        if not self.is_set():
            op.emit(E.EVENT_WAIT_BLOCKED)
        try:
            await super().wait()
        except BaseException as error:
            op.emit(
                E.EVENT_WAIT_FAILED,
                reason=_why(error),
                error=type(error).__name__,
            )
            raise
        op.emit(E.EVENT_WAIT_COMPLETED)
        return True


class TracedAsyncCondition(_BaseCondition):
    """``asyncio.Condition`` that records waits and notifications.

    Args:
        lock: The associated lock. Defaults to a ``TracedAsyncLock`` so its
            release and re-acquisition appear in the recording.
        name: Display name in the viewer.
    """

    def __init__(self, lock: Any = None, *, name: str | None = None) -> None:
        if lock is None and active_recorder() is not None:
            lock = TracedAsyncLock(name=f"{name} lock" if name else None)
        super().__init__(lock)
        self._cz_name = name
        rec = active_recorder()
        if rec is not None:
            self._cz_rid(rec)

    def _cz_rid(self, rec: Recorder) -> str:
        meta: dict[str, Any] = {}
        lock_rid = getattr(self._lock, "_cz_rid", None)  # ty: ignore[unresolved-attribute]
        if lock_rid is not None:
            meta["lock"] = lock_rid(rec)
        return rec.resource_id(self, "condition", self._cz_name, meta)

    async def wait(self) -> bool:  # ty: ignore[invalid-method-override]
        """``Condition.wait``: release the lock, suspend, re-acquire it."""
        rec = active_recorder()
        if rec is None or not self.locked():
            return await super().wait()  # the base raises RuntimeError
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        op.emit(E.CONDITION_WAIT_STARTED)
        try:
            await super().wait()
        except BaseException as error:
            op.emit(
                E.CONDITION_WAIT_FAILED,
                reason=_why(error),
                error=type(error).__name__,
            )
            raise
        op.emit(E.CONDITION_WAIT_COMPLETED)
        return True

    def _cz_notify(self, n: int, everyone: bool) -> None:
        rec = active_recorder()
        if rec is not None and self.locked():
            waiting = sum(not fut.done() for fut in self._waiters)
            rec.emit(
                E.CONDITION_NOTIFY,
                resource_id=self._cz_rid(rec),
                source=rec.capture_source(),
                metadata={
                    "n": n,
                    "all": everyone,
                    "waiting": waiting,
                    "woken": min(n, waiting),
                },
            )
        super().notify(n)

    def notify(self, n: int = 1) -> None:
        """``Condition.notify``; the lock stays held by the caller."""
        self._cz_notify(n, False)

    def notify_all(self) -> None:
        """``Condition.notify_all``."""
        self._cz_notify(len(self._waiters), True)
