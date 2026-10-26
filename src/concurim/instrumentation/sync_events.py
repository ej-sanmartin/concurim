"""Instrumented ``threading.Event`` and ``threading.Condition``.

Both subclass the standard classes and behave exactly like them outside a
``concurim.record()`` block.

Event: ``event.set`` is emitted just *before* the flag flips, so every wait it
releases completes with a larger sequence number.

Condition: ``wait`` is recorded as started and then completed (notified) or
timed out; the associated lock's own events (it is a ``TracedRLock`` unless
you pass one) show the release on entry and the *re-acquisition* on wake-up.
``notify`` is emitted while the notifier still holds the lock, because a
notification does not release it. Which waiter wakes is not recorded: the
standard library happens to wake the oldest first, but that is not a
guarantee, so the replay never claims it.
"""

from __future__ import annotations

import threading
from typing import Any

from concurim.instrumentation.queue_support import _Op
from concurim.instrumentation.sync import TracedRLock
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)
# ``Condition.wait_for`` and ``Event.wait`` call our overrides from here; the
# event should be attributed to the user's line, not the library's.
mark_internal(threading.__file__)

# Bound once: the classes may be replaced while auto-instrumenting.
_BaseEvent = threading.Event
_BaseCondition = threading.Condition


class TracedEvent(_BaseEvent):
    """``threading.Event`` that records set, clear and waits.

    Args:
        name: Display name in the viewer.
    """

    _cz_on = True

    def __init__(self, *, name: str | None = None) -> None:
        super().__init__()
        self._cz_name = name
        rec = active_recorder() if self._cz_on else None
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
        rec = active_recorder() if self._cz_on else None
        if rec is not None:
            self._cz_emit(rec, E.EVENT_SET, already_set=self.is_set())
        super().set()

    def clear(self) -> None:
        """``Event.clear``."""
        rec = active_recorder() if self._cz_on else None
        if rec is not None:
            self._cz_emit(rec, E.EVENT_CLEARED, was_set=self.is_set())
        super().clear()

    def wait(self, timeout: float | None = None) -> bool:
        """``Event.wait``; an unset event makes the caller wait."""
        rec = active_recorder() if self._cz_on else None
        if rec is None:
            return super().wait(timeout)
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        op.emit(E.EVENT_WAIT_STARTED, timeout=timeout)
        if not self.is_set():
            op.emit(E.EVENT_WAIT_BLOCKED)
        try:
            got = super().wait(timeout)
        except BaseException as error:
            op.emit(
                E.EVENT_WAIT_FAILED,
                reason="exception",
                error=type(error).__name__,
            )
            raise
        if got:
            op.emit(E.EVENT_WAIT_COMPLETED)
        else:
            op.emit(E.EVENT_WAIT_TIMEOUT, timeout=timeout)
        return got


class TracedCondition(_BaseCondition):
    """``threading.Condition`` that records waits and notifications.

    Args:
        lock: The associated lock. Defaults to a ``TracedRLock`` so its
            release and re-acquisition appear in the recording.
        name: Display name in the viewer.
    """

    _cz_on = True

    def __init__(self, lock: Any = None, *, name: str | None = None) -> None:
        if lock is None and self._cz_on and active_recorder() is not None:
            lock = TracedRLock(name=f"{name} lock" if name else None)
        super().__init__(lock)  # ty: ignore[invalid-argument-type]
        self._cz_name = name
        rec = active_recorder() if self._cz_on else None
        if rec is not None:
            self._cz_rid(rec)

    def _cz_rid(self, rec: Recorder) -> str:
        meta: dict[str, Any] = {}
        lock_rid = getattr(self._lock, "_cz_rid", None)  # ty: ignore[unresolved-attribute]
        if lock_rid is not None:
            meta["lock"] = lock_rid(rec)
        return rec.resource_id(self, "condition", self._cz_name, meta)

    def wait(self, timeout: float | None = None) -> bool:
        """``Condition.wait``: release the lock, wait, re-acquire it."""
        rec = active_recorder() if self._cz_on else None
        if rec is None or not self._is_owned():  # ty: ignore[unresolved-attribute]
            return super().wait(timeout)  # the base raises RuntimeError
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        op.emit(E.CONDITION_WAIT_STARTED, timeout=timeout)
        try:
            notified = super().wait(timeout)
        except BaseException as error:
            op.emit(
                E.CONDITION_WAIT_FAILED,
                reason="exception",
                error=type(error).__name__,
            )
            raise
        if notified:
            op.emit(E.CONDITION_WAIT_COMPLETED)
        else:
            op.emit(E.CONDITION_WAIT_TIMEOUT, timeout=timeout)
        return notified

    def _cz_notify(self, n: int, everyone: bool) -> None:
        rec = active_recorder() if self._cz_on else None
        if rec is not None and self._is_owned():  # ty: ignore[unresolved-attribute]
            waiting = len(self._waiters)  # ty: ignore[unresolved-attribute]
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
        self._cz_notify(len(self._waiters), True)  # ty: ignore[unresolved-attribute]
