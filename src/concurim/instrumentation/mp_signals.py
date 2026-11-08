"""Instrumented ``multiprocessing.Event`` and ``multiprocessing.Barrier``.

Same events as the thread versions (``event.set``, ``event.wait.*``,
``barrier.wait.*``), so the viewer draws them the same way. They subclass
the real classes, so they still work across processes and survive pickling
for a ``spawn`` child. In a worker, events go through the pipe the worker
inherited, under the resource id the parent registered (see ``mp_sync`` and
``mp_events``). The order between two processes is approximate.
"""

from __future__ import annotations

import multiprocessing
import multiprocessing.synchronize as _sync
import threading
from typing import Any

from concurim.instrumentation.mp_sync import MPOp, MPReporting
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)

# Bound once: the ``synchronize`` names may be replaced while patched.
_BaseEvent = _sync.Event
_BaseBarrier = _sync.Barrier


class TracedMPEvent(MPReporting, _BaseEvent):
    """``multiprocessing.Event`` that records set, clear and waits.

    Args:
        ctx: Multiprocessing context (default: the default context).
        name: Display name in the viewer.
    """

    def __init__(self, *, ctx: Any = None, name: str | None = None) -> None:
        super().__init__(ctx=ctx or multiprocessing.get_context())
        self._cz_name = name
        rec = active_recorder() if self._cz_on else None
        if rec is not None:
            self._cz_rid(rec)

    def _cz_rid(self, rec: Recorder) -> str:
        rid = rec.resource_id(self, "event", self._cz_name, {"is_set": False})
        self._cz_id = rid
        return rid

    def __getstate__(self) -> dict[str, Any]:
        rec = active_recorder()
        if rec is not None and self._cz_on:
            self._cz_rid(rec)  # a child must know the id
        state = dict(self.__dict__)
        state.pop("_cz_reg", None)  # the recorder's note: not picklable
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)

    def set(self) -> None:
        """``Event.set``; recorded before the flag flips."""
        target = self._cz_target()
        if target is not None:
            MPOp(*target).emit(E.EVENT_SET, already_set=self.is_set())
        super().set()

    def clear(self) -> None:
        """``Event.clear``."""
        target = self._cz_target()
        if target is not None:
            MPOp(*target).emit(E.EVENT_CLEARED, was_set=self.is_set())
        super().clear()

    def wait(self, timeout: float | None = None) -> bool:
        """``Event.wait``; an unset event makes the caller wait."""
        target = self._cz_target()
        if target is None:
            return super().wait(timeout)
        op = MPOp(*target)
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


class TracedMPBarrier(MPReporting, _BaseBarrier):
    """``multiprocessing.Barrier`` that records arrivals, abort and reset.

    Args:
        parties: How many arrivals release the barrier.
        action: Optional callable run by the last arrival before release.
        timeout: Default timeout for ``wait``, in seconds.
        ctx: Multiprocessing context (default: the default context).
        name: Display name in the viewer.
    """

    _timeout: Any  # set by the real ``Barrier.__setstate__``
    _action: Any

    def __init__(
        self,
        parties: int,
        action: Any = None,
        timeout: float | None = None,
        *,
        ctx: Any = None,
        name: str | None = None,
    ) -> None:
        super().__init__(
            parties, action, timeout, ctx=ctx or multiprocessing.get_context()
        )
        self._cz_name = name
        rec = active_recorder() if self._cz_on else None
        if rec is not None:
            self._cz_rid(rec)

    def _cz_rid(self, rec: Recorder) -> str:
        rid = rec.resource_id(
            self,
            "barrier",
            self._cz_name,
            {
                "parties": self.parties,
                "timeout": self._timeout,
                "action": self._action is not None,
            },
        )
        self._cz_id = rid
        return rid

    def wait(self, timeout: float | None = None) -> int:
        """``Barrier.wait``; every arrival but the last one blocks."""
        target = self._cz_target()
        if target is None:
            return super().wait(timeout)
        op = MPOp(*target)
        waiting, parties = self.n_waiting, self.parties
        op.emit(
            E.BARRIER_WAIT_STARTED,
            timeout=timeout,
            waiting=waiting,
            parties=parties,
        )
        if not self.broken and waiting < parties - 1:
            op.emit(E.BARRIER_WAIT_BLOCKED, waiting=waiting, parties=parties)
        try:
            index = super().wait(timeout)
        except BaseException as error:
            broken = bool(self.broken)
            if isinstance(error, threading.BrokenBarrierError):
                op.emit(E.BARRIER_WAIT_FAILED, reason="broken", broken=broken)
            else:
                op.emit(
                    E.BARRIER_WAIT_FAILED,
                    reason="exception",
                    error=type(error).__name__,
                    broken=broken,
                )
            raise
        op.emit(E.BARRIER_WAIT_COMPLETED, index=index, parties=self.parties)
        return index

    def abort(self) -> None:
        """``Barrier.abort``; waiting arrivals fail and it stays broken."""
        self._cz_signal(E.BARRIER_ABORT)
        super().abort()

    def reset(self) -> None:
        """``Barrier.reset``; waiting arrivals fail, then a new party starts."""
        self._cz_signal(E.BARRIER_RESET)
        super().reset()

    def _cz_signal(self, event_type: str) -> None:
        target = self._cz_target()
        if target is not None:
            MPOp(*target).emit(
                event_type, waiting=self.n_waiting, parties=self.parties
            )

    def __getstate__(self) -> tuple[Any, ...]:
        rec = active_recorder()
        if rec is not None and self._cz_on:
            self._cz_rid(rec)  # a child must know the id
        base: tuple[Any, ...] = super().__getstate__()  # ty: ignore
        return (*base, self._cz_id, self._cz_name, self._cz_on)

    def __setstate__(self, state: tuple[Any, ...]) -> None:
        # The real ``__init__`` passes the five base fields; a pickle adds ours.
        if len(state) > 5:
            self._cz_id, self._cz_name, self._cz_on = state[5:]
        super().__setstate__(state[:5])  # ty: ignore
