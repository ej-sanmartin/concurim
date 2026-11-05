"""Instrumented ``multiprocessing`` locks and semaphores.

They subclass the real ones, so they still work across processes and
survive pickling for a ``spawn`` child. In the process that records they emit
events directly; in a worker they report through the pipe the worker
inherited (see ``mp_events``), under the *same* resource id, so one lock
shows every process that takes it.

``SemLock`` binds ``acquire`` and ``release`` as instance attributes, which
would hide methods defined on a subclass, so ``_make_methods`` is where the
wrapping happens.
"""

from __future__ import annotations

import multiprocessing.synchronize as _sync
from typing import Any

from concurim.instrumentation.mp_events import (
    caller_where,
    child_op,
    report_event,
    reporting,
)
from concurim.instrumentation.sync import traced_acquire
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)

# Bound once: the ``synchronize`` names may be replaced while patched.
_BaseLock = _sync.Lock
_BaseRLock = _sync.RLock
_BaseSemaphore = _sync.Semaphore
_BaseBounded = _sync.BoundedSemaphore


class MPOp:
    """Event context for one call: records here, or reports to the parent.

    Same ``emit`` shape as the thread-side context, so ``traced_acquire``
    drives both.
    """

    __slots__ = ("rid", "op", "source", "where")

    def __init__(self, rid: str, rec: Recorder | None) -> None:
        self.rid = rid
        if rec is not None:
            self.op = rec.new_operation_id()
            self.source = rec.capture_source()
            self.where = None
        else:
            self.op = child_op()
            self.source = None
            self.where = caller_where()

    def emit(
        self,
        event_type: str,
        object_id: str | None = None,
        caused_by: str | None = None,
        **meta: Any,
    ) -> None:
        rec = active_recorder()
        if rec is not None:
            rec.emit(
                event_type,
                resource_id=self.rid,
                operation_id=self.op,
                source=self.source,
                metadata=meta,
            )
        else:
            report_event(event_type, self.rid, self.op, meta, self.where)


class _MPHeld:
    """Shared plumbing for the four primitives (mixed in before the base)."""

    _cz_kind = "lock"  # event prefix: lock | semaphore
    _cz_name: str | None = None
    _cz_meta: dict[str, Any]
    _cz_on = True
    _cz_id: str | None = None  # resource id, known to every process
    _semlock: Any  # set by the real SemLock this is mixed in before

    def _cz_setup(self, name: str | None, **meta: Any) -> None:
        self._cz_name = name
        self._cz_meta = meta
        rec = active_recorder()
        if rec is not None and self._cz_on:
            self._cz_rid(rec)

    def _cz_rid(self, rec: Recorder) -> str:
        rid = rec.resource_id(self, self._cz_kind, self._cz_name, self._cz_meta)
        self._cz_id = rid
        return rid

    def _cz_target(self) -> tuple[str, Recorder | None] | None:
        """``(resource id, recorder or None)`` if events should be made."""
        if not self._cz_on:
            return None
        rec = active_recorder()
        if rec is not None:
            return self._cz_rid(rec), rec
        if self._cz_id is not None and reporting():
            return self._cz_id, None
        return None

    def _make_methods(self) -> None:
        super()._make_methods()  # ty: ignore[unresolved-attribute]
        self._cz_raw = (self.acquire, self.release)
        self.acquire = self._cz_acquire
        self.release = self._cz_release

    def _cz_acquire(
        self, block: bool = True, timeout: float | None = None
    ) -> bool:
        raw_acquire = self._cz_raw[0]
        target = self._cz_target()
        if target is None:
            return raw_acquire(block, timeout)
        op = MPOp(*target)
        return traced_acquire(
            op,  # ty: ignore[invalid-argument-type]
            self._cz_kind,
            bool(block),
            timeout,
            lambda: raw_acquire(False),
            lambda: raw_acquire(True, timeout),
        )

    def _cz_refusal(self) -> str | None:
        """Why a release would fail, or ``None`` if it would succeed."""
        return None

    def _cz_release(self) -> None:
        target = self._cz_target()
        if target is not None:
            op = MPOp(*target)
            reason = self._cz_refusal()
            if reason is None:
                op.emit(f"{self._cz_kind}.released", count=1)
            elif self._cz_kind == "lock":
                op.emit("lock.release.failed", reason=reason)
        self._cz_raw[1]()

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        self.release()

    def __getstate__(self) -> tuple[Any, ...]:
        rec = active_recorder()
        if rec is not None and self._cz_on:
            self._cz_rid(rec)  # a child must know the id
        return (
            super().__getstate__(),
            self._cz_id,
            self._cz_name,
            self._cz_on,
        )

    def __setstate__(self, state: tuple[Any, ...]) -> None:
        base, self._cz_id, self._cz_name, self._cz_on = state
        self._cz_meta = {}
        super().__setstate__(base)  # ty: ignore[unresolved-attribute]


class TracedMPLock(_MPHeld, _BaseLock):
    """``multiprocessing.Lock`` that records acquire and release.

    Args:
        ctx: Multiprocessing context (default: the default context).
        name: Display name in the viewer.
    """

    def __init__(self, *, ctx: Any = None, name: str | None = None) -> None:
        super().__init__(ctx=ctx)
        self._cz_setup(name, kind="lock", value=1)

    def _cz_refusal(self) -> str | None:
        # Any process may release a Lock, but only while it is taken.
        return None if self._semlock._is_zero() else "not_locked"


class TracedMPRLock(_MPHeld, _BaseRLock):
    """``multiprocessing.RLock`` that records every acquire and release.

    Args:
        ctx: Multiprocessing context (default: the default context).
        name: Display name in the viewer.
    """

    def __init__(self, *, ctx: Any = None, name: str | None = None) -> None:
        super().__init__(ctx=ctx)
        self._cz_setup(name, kind="rlock", value=1)

    def _cz_refusal(self) -> str | None:
        if self._semlock._is_mine():
            return None
        return "not_owner" if self._semlock._is_zero() else "not_acquired"


class TracedMPSemaphore(_MPHeld, _BaseSemaphore):
    """``multiprocessing.Semaphore`` that records acquire and release.

    Args:
        value: Initial number of permits.
        ctx: Multiprocessing context (default: the default context).
        name: Display name in the viewer.
    """

    _cz_kind = "semaphore"

    def __init__(
        self, value: int = 1, *, ctx: Any = None, name: str | None = None
    ) -> None:
        super().__init__(value, ctx=ctx)
        self._cz_setup(name, kind="semaphore", value=value, bounded=False)


class TracedMPBoundedSemaphore(_MPHeld, _BaseBounded):
    """``multiprocessing.BoundedSemaphore`` that records its operations.

    Args:
        value: Initial (and maximum) number of permits.
        ctx: Multiprocessing context (default: the default context).
        name: Display name in the viewer.
    """

    _cz_kind = "semaphore"

    def __init__(
        self, value: int = 1, *, ctx: Any = None, name: str | None = None
    ) -> None:
        super().__init__(value, ctx=ctx)
        self._cz_setup(name, kind="semaphore", value=value, bounded=True)

    def _cz_refusal(self) -> str | None:
        try:
            full = self._semlock._get_value() >= self._semlock.maxvalue
        except NotImplementedError:  # macOS cannot read a semaphore's value
            return None
        return "over_release" if full else None
