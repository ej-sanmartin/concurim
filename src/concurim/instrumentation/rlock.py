"""Instrumented ``threading.RLock``.

Split from ``sync`` to keep both modules short. Every acquire (including a
re-entry by the owner) and every release is one event; a release the real
lock refuses (not the owner, or not held at all) is recorded as
``lock.release.failed`` before the ``RuntimeError`` reaches the caller.
"""

from __future__ import annotations

import threading
from typing import Any

from concurim.instrumentation.queue_support import _Op
from concurim.instrumentation.sync import _Held, _invalid, traced_acquire
from concurim.recorder.collector import mark_internal
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)

# Bound once: ``threading.RLock`` may be replaced while auto-instrumenting.
_new_rlock = threading.RLock


class TracedRLock(_Held):
    """Drop-in ``threading.RLock`` that records every acquire and release.

    Args:
        name: Display name in the viewer.
    """

    _cz_kind = "lock"

    def __init__(self, *, name: str | None = None) -> None:
        self._lock = _new_rlock()
        self._cz_name = name
        self._cz_meta = {"kind": "rlock", "value": 1}
        rec = active_recorder()
        if rec is not None:
            self._cz_rid(rec)

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """``RLock.acquire``; each (re-)acquisition is one event."""
        rec = active_recorder()
        if rec is None or _invalid(blocking, timeout):
            return self._lock.acquire(blocking, timeout)
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        return traced_acquire(
            op,
            "lock",
            blocking,
            timeout,
            lambda: self._lock.acquire(False),
            lambda: self._lock.acquire(True, timeout),
        )

    def release(self) -> None:
        """``RLock.release``; a refused release is recorded, then raised."""
        rec = active_recorder()
        if rec is not None:
            if self._is_owned():
                self._cz_released(rec)
            else:
                held = self.locked()  # someone else holds it, or nobody
                self._cz_release_failed(
                    rec, "not_owner" if held else "not_acquired"
                )
        self._lock.release()

    def _is_owned(self) -> bool:
        return self._lock._is_owned()  # ty: ignore[unresolved-attribute]

    def _release_save(self) -> Any:
        """Release every level at once (``Condition.wait`` uses this)."""
        rec = active_recorder()
        if rec is not None and self._is_owned():
            levels = getattr(self._lock, "_recursion_count", lambda: 1)()
            self._cz_released(rec, count=levels)
        return self._lock._release_save()  # ty: ignore[unresolved-attribute]

    def _acquire_restore(self, state: Any) -> None:
        """Re-acquire every released level (``Condition.wait`` wake-up)."""
        rec = active_recorder()
        if rec is None:
            self._lock._acquire_restore(state)  # ty: ignore[unresolved-attribute]
            return
        levels = state[0]
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        op.emit("lock.acquire.started", blocking=True, timeout=None)
        if not self._lock.acquire(False):
            op.emit("lock.acquire.blocked")
            self._lock.acquire()
        for _ in range(levels - 1):
            self._lock.acquire()
        op.emit("lock.acquire.completed", count=levels)

    def locked(self) -> bool:
        """Whether any thread holds it (``Condition`` needs this on 3.14)."""
        if self._is_owned():
            return True
        if self._lock.acquire(False):
            self._lock.release()
            return False
        return True

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        self.release()
