"""Instrumented ``threading.Barrier`` and ``asyncio.Barrier``.

A barrier releases every arrival together once ``parties`` threads or tasks
have called ``wait``. Earlier arrivals are blocked. ``abort`` and ``reset``
wake them with ``BrokenBarrierError``; a timed-out wait does the same and
leaves the barrier broken. The internal condition a barrier uses for itself
is not recorded: only the barrier's own arrivals are.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from concurim.instrumentation.auto_support import creation_name, user_caller
from concurim.instrumentation.queue_support import _Op
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)

_BROKEN = (threading.BrokenBarrierError, asyncio.BrokenBarrierError)
_BaseBarrier = threading.Barrier
_BaseAsyncBarrier = asyncio.Barrier


def _rid(owner: Any, rec: Recorder) -> str:
    timeout = getattr(owner, "_timeout", None)
    action = getattr(owner, "_action", None)
    return rec.resource_id(
        owner,
        "barrier",
        owner._cz_name,
        {
            "parties": owner.parties,
            "timeout": timeout,
            "action": action is not None,
        },
    )


def _begin(owner: Any, rec: Recorder, timeout: float | None) -> _Op:
    """Emit the arrival, and that it will block when it is not the last."""
    op = _Op(rec, _rid(owner, rec), rec.capture_source())
    waiting = owner.n_waiting
    op.emit(
        E.BARRIER_WAIT_STARTED,
        timeout=timeout,
        waiting=waiting,
        parties=owner.parties,
    )
    if not owner.broken and waiting < owner.parties - 1:
        op.emit(
            E.BARRIER_WAIT_BLOCKED,
            waiting=waiting,
            parties=owner.parties,
        )
    return op


def _finish(op: _Op, owner: Any, index: int) -> int:
    op.emit(E.BARRIER_WAIT_COMPLETED, index=index, parties=owner.parties)
    return index


def _signal(owner: Any, event_type: str) -> None:
    """Record abort or reset before the barrier wakes its arrivals."""
    rec = active_recorder() if owner._cz_on else None
    if rec is None:
        return
    rec.emit(
        event_type,
        resource_id=_rid(owner, rec),
        source=rec.capture_source(),
        metadata={"waiting": owner.n_waiting, "parties": owner.parties},
    )


def _fail(op: _Op, owner: Any, error: BaseException) -> None:
    broken = bool(getattr(owner, "broken", False))
    if isinstance(error, _BROKEN):
        op.emit(E.BARRIER_WAIT_FAILED, reason="broken", broken=broken)
    else:
        op.emit(
            E.BARRIER_WAIT_FAILED,
            reason="exception",
            error=type(error).__name__,
            broken=broken,
        )


class TracedBarrier(_BaseBarrier):
    """``threading.Barrier`` that records arrivals, abort and reset.

    Args:
        parties: How many arrivals release the barrier.
        action: Optional callable run by the last arrival before release.
        timeout: Default timeout for ``wait``, in seconds.
        name: Display name in the viewer.
    """

    _cz_on = True

    def __init__(
        self,
        parties: int,
        action: Any = None,
        timeout: float | None = None,
        *,
        name: str | None = None,
    ) -> None:
        super().__init__(parties, action, timeout)
        self._cz_name = name
        rec = active_recorder() if self._cz_on else None
        if rec is not None:
            _rid(self, rec)

    def wait(self, timeout: float | None = None) -> int:
        """``Barrier.wait``; every arrival but the last one blocks."""
        rec = active_recorder() if self._cz_on else None
        if rec is None:
            return super().wait(timeout)
        op = _begin(self, rec, timeout)
        try:
            index = super().wait(timeout)
        except BaseException as error:
            _fail(op, self, error)
            raise
        return _finish(op, self, index)

    def abort(self) -> None:
        """``Barrier.abort``; waiting arrivals fail and it stays broken."""
        _signal(self, E.BARRIER_ABORT)
        super().abort()

    def reset(self) -> None:
        """``Barrier.reset``; waiting arrivals fail, then a new party starts."""
        _signal(self, E.BARRIER_RESET)
        super().reset()


class TracedAsyncBarrier(_BaseAsyncBarrier):
    """``asyncio.Barrier`` that records the same events as ``TracedBarrier``.

    The standard library's async barrier has no action and no timeout.

    Args:
        parties: How many arrivals release the barrier.
        name: Display name in the viewer.
    """

    _cz_on = True

    def __init__(self, parties: int, *, name: str | None = None) -> None:
        super().__init__(parties)
        self._cz_name = name
        rec = active_recorder() if self._cz_on else None
        if rec is not None:
            _rid(self, rec)

    async def wait(self) -> int:
        """``Barrier.wait``; tasks before the last one suspend."""
        rec = active_recorder() if self._cz_on else None
        if rec is None:
            return await super().wait()
        op = _begin(self, rec, None)
        try:
            index = await super().wait()
        except BaseException as error:
            _fail(op, self, error)
            raise
        return _finish(op, self, index)

    async def abort(self) -> None:
        """``Barrier.abort``."""
        _signal(self, E.BARRIER_ABORT)
        await super().abort()

    async def reset(self) -> None:
        """``Barrier.reset``."""
        _signal(self, E.BARRIER_RESET)
        await super().reset()


class AutoBarrier(TracedBarrier):
    """Traced only when user code creates the barrier."""

    def __init__(
        self,
        parties: int,
        action: Any = None,
        timeout: float | None = None,
    ) -> None:
        self._cz_on = user_caller(1)
        super().__init__(
            parties,
            action,
            timeout,
            name=creation_name("Barrier") if self._cz_on else None,
        )


class AutoAsyncBarrier(TracedAsyncBarrier):
    """Traced only when user code creates the barrier."""

    def __init__(self, parties: int) -> None:
        self._cz_on = user_caller(1)
        super().__init__(
            parties,
            name=creation_name("Barrier") if self._cz_on else None,
        )
