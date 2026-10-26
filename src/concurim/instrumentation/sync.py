"""Instrumented ``threading`` locks and semaphores.

``TracedLock`` and ``TracedRLock`` wrap the real primitives (the C lock types
cannot be subclassed); ``TracedSemaphore`` subclasses ``threading.Semaphore``.
Outside a ``concurim.record()`` block they behave like the originals.

Ordering: ``released`` is emitted just *before* the real release, so the next
holder's ``acquire.completed`` (emitted after its acquire returns) always has
a larger sequence number. ``blocked`` means the primitive was unavailable when
the call first tried, which is what the caller observed.
"""

from __future__ import annotations

import _thread
import threading
from collections.abc import Callable
from typing import Any

from concurim.instrumentation.queue_support import _Op
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)

# Bound once: ``threading.Semaphore`` may be replaced while auto-instrumenting.
_BaseSemaphore = threading.Semaphore
_BaseBoundedSemaphore = threading.BoundedSemaphore
_new_rlock = threading.RLock


def _invalid(blocking: bool, timeout: float | None) -> bool:
    """Argument combinations the real primitives reject themselves."""
    if timeout is None:
        return False
    return (not blocking and timeout != -1) or (timeout < 0 and timeout != -1)


def traced_acquire(
    op: _Op,
    kind: str,
    blocking: bool,
    timeout: float | None,
    fast: Callable[[], bool],
    slow: Callable[[], bool],
) -> bool:
    """Try without blocking; if that fails, record and block.

    Args:
        op: Event context for this call.
        kind: ``"lock"`` or ``"semaphore"`` (the event prefix).
        blocking: The caller's ``blocking`` argument.
        timeout: The caller's ``timeout`` argument (for the trace only).
        fast: Non-blocking attempt, returns whether it acquired.
        slow: Blocking attempt, returns whether it acquired in time.

    Returns:
        Whether the primitive was acquired.
    """
    prefix = f"{kind}.acquire"
    op.emit(f"{prefix}.started", blocking=blocking, timeout=timeout)
    try:
        if fast():
            op.emit(f"{prefix}.completed")
            return True
        if not blocking:
            op.emit(f"{prefix}.failed", reason="nonblocking")
            return False
        op.emit(f"{prefix}.blocked")
        got = slow()
    except BaseException as error:
        op.emit(
            f"{prefix}.failed", reason="exception", error=type(error).__name__
        )
        raise
    if got:
        op.emit(f"{prefix}.completed")
    else:
        op.emit(f"{prefix}.failed", reason="timeout", timeout=timeout)
    return got


class _Held:
    """Shared plumbing: a resource id registered on first recorded use."""

    _cz_name: str | None
    _cz_meta: dict[str, Any]
    _cz_kind: str = "lock"

    def _cz_rid(self, rec: Recorder) -> str:
        return rec.resource_id(
            self, self._cz_kind, self._cz_name, self._cz_meta
        )

    def _cz_released(self, rec: Recorder, **meta: Any) -> None:
        rec.emit(
            f"{self._cz_kind}.released",
            resource_id=self._cz_rid(rec),
            source=rec.capture_source(),
            metadata=meta,
        )


class TracedLock(_Held):
    """Drop-in ``threading.Lock`` that records acquire and release.

    Args:
        name: Display name in the viewer.
    """

    _cz_kind = "lock"

    def __init__(self, *, name: str | None = None) -> None:
        self._lock = _thread.allocate_lock()
        self._cz_name = name
        self._cz_meta = {"kind": "lock", "value": 1}
        rec = active_recorder()
        if rec is not None:
            self._cz_rid(rec)

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """``Lock.acquire``, recording how long the caller had to wait."""
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
        """``Lock.release``."""
        rec = active_recorder()
        if rec is not None and self._lock.locked():
            self._cz_released(rec)
        self._lock.release()

    def locked(self) -> bool:
        """Whether the lock is held."""
        return self._lock.locked()

    def _is_owned(self) -> bool:
        # ``Condition`` asks this on every wait/notify; its default probes
        # with a real acquire, which would show up as phantom events.
        return self._lock.locked()

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        self.release()


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
        """``RLock.release``."""
        rec = active_recorder()
        if rec is not None and self._is_owned():
            self._cz_released(rec)
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


class TracedSemaphore(_Held, _BaseSemaphore):
    """``threading.Semaphore`` that records acquire and release.

    Args:
        value: Initial number of permits.
        name: Display name in the viewer.
    """

    _cz_on = True
    _cz_kind = "semaphore"

    def __init__(self, value: int = 1, *, name: str | None = None) -> None:
        super().__init__(value)
        self._cz_name = name
        self._cz_meta = {
            "kind": "semaphore",
            "value": value,
            "bounded": isinstance(self, _BaseBoundedSemaphore),
        }
        rec = active_recorder()
        if rec is not None and self._cz_on:
            self._cz_rid(rec)

    def acquire(
        self, blocking: bool = True, timeout: float | None = None
    ) -> bool:
        """``Semaphore.acquire``, recording waits."""
        rec = active_recorder() if self._cz_on else None
        if rec is None or _invalid(blocking, timeout):
            return _BaseSemaphore.acquire(self, blocking, timeout)
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        return traced_acquire(
            op,
            "semaphore",
            blocking,
            timeout,
            lambda: _BaseSemaphore.acquire(self, False),
            lambda: _BaseSemaphore.acquire(self, True, timeout),
        )

    __enter__ = acquire

    def release(self, n: int = 1) -> None:
        """``Semaphore.release``."""
        rec = active_recorder() if self._cz_on else None
        initial = getattr(self, "_initial_value", None)
        over = initial is not None and self._value + n > initial
        if rec is not None and n >= 1 and not over:
            self._cz_released(rec, count=n)
        super().release(n)


class TracedBoundedSemaphore(TracedSemaphore, _BaseBoundedSemaphore):
    """``threading.BoundedSemaphore`` that records acquire and release."""
