"""A ``multiprocessing.Value`` whose reads and writes are recorded.

Same idea as ``TracedCell``, for a value that lives in shared memory. Each
``.value`` read or write is one event, made while the value's own lock is
held (as the standard library does), so the replay shows exactly which
lock each process held at each access. ``Value(..., lock=False)`` is
traced too, which is where an unprotected access shows up. Reading through
``get_obj()`` bypasses the wrapper and is not seen.
"""

from __future__ import annotations

import ctypes
import multiprocessing
import multiprocessing.context
import multiprocessing.sharedctypes as _sc
from typing import Any

from concurim.instrumentation.cells import value_meta
from concurim.instrumentation.mp_events import (
    caller_where,
    child_op,
    raw_meta,
    report_event,
    reporting,
)
from concurim.instrumentation.mp_sync import TracedMPRLock
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)

# Bound once: ``sharedctypes.Value`` may be replaced while auto-instrumenting.
_REAL_VALUE = _sc.Value


class TracedValue(_sc.SynchronizedBase):
    """Synchronized shared scalar that records every access.

    Args:
        obj: The raw ctypes value in shared memory.
        lock: The lock guarding it, or ``None`` for an unguarded value.
        name: Display name in the viewer.
        rid: Resource id, passed along when a child process rebuilds it.
    """

    def __init__(
        self,
        obj: Any,
        lock: Any = None,
        *,
        name: str | None = None,
        rid: str | None = None,
    ) -> None:
        self._obj = obj
        self._lock = lock
        self._cz_name = name
        self._cz_id = rid
        if lock is not None:
            self.acquire = lock.acquire
            self.release = lock.release
        rec = active_recorder()
        if rec is not None and rid is None:
            self._cz_rid(rec)

    def _cz_rid(self, rec: Recorder) -> str:
        rid = rec.resource_id(
            self, "cell", self._cz_name, value_meta(rec, self._obj.value)
        )
        self._cz_id = rid
        return rid

    def _cz_emit(self, kind: str, value: Any) -> None:
        rec = active_recorder()
        if rec is not None:
            rec.emit(
                kind,
                resource_id=self._cz_rid(rec),
                source=rec.capture_source(),
                metadata=value_meta(rec, value),
            )
        elif self._cz_id is not None and reporting():
            report_event(
                kind, self._cz_id, child_op(), raw_meta(value), caller_where()
            )

    def __enter__(self) -> Any:
        return self._lock.__enter__() if self._lock is not None else None

    def __exit__(self, *args: Any) -> Any:
        return self._lock.__exit__(*args) if self._lock is not None else None

    def __reduce__(self) -> tuple[Any, ...]:
        multiprocessing.context.assert_spawning(self)
        rec = active_recorder()
        if rec is not None and self._cz_id is None:
            self._cz_rid(rec)
        return _rebuild, (self._obj, self._lock, self._cz_name, self._cz_id)

    @property
    def value(self) -> Any:
        """The shared value; the read is recorded under the lock."""
        if self._lock is not None:
            self.acquire()
        try:
            value = self._obj.value
            self._cz_emit(E.CELL_READ, value)
            return value
        finally:
            if self._lock is not None:
                self.release()

    @value.setter
    def value(self, new: Any) -> None:
        if self._lock is not None:
            self.acquire()
        try:
            self._obj.value = new
            self._cz_emit(E.CELL_WRITE, new)
        finally:
            if self._lock is not None:
                self.release()


def _rebuild(
    obj: Any, lock: Any, name: str | None, rid: str | None
) -> TracedValue:
    """Unpickle in a child: same shared memory, same lock, same id."""
    return TracedValue(obj, lock, name=name, rid=rid)


def traced_value(
    typecode_or_type: Any,
    *args: Any,
    lock: Any = True,
    name: str | None = None,
    ctx: Any = None,
) -> Any:
    """``multiprocessing.Value`` with every access recorded.

    Takes the same arguments plus ``name``. Types other than a plain
    scalar (a ctypes structure or array) are returned as the standard
    library builds them, untraced.

    Args:
        typecode_or_type: A ``ctypes`` type or typecode such as ``"i"``.
        *args: Initial value, as for ``multiprocessing.Value``.
        lock: ``True`` (a recorded ``RLock``), ``False`` (no lock), or a
            lock object.
        name: Display name in the viewer.
        ctx: Multiprocessing context for the lock.

    Returns:
        A ``TracedValue``, or the standard object for non-scalar types.
    """
    obj = _sc.RawValue(typecode_or_type, *args)
    if not isinstance(obj, ctypes._SimpleCData):
        return _REAL_VALUE(typecode_or_type, *args, lock=lock, ctx=ctx)
    if lock is False:
        guard = None
    elif lock in (True, None):
        guard = TracedMPRLock(ctx=ctx, name=f"{name} lock" if name else None)
    elif hasattr(lock, "acquire"):
        guard = lock
    else:
        raise AttributeError(f"{lock!r} has no method 'acquire'")
    return TracedValue(obj, guard, name=name)
