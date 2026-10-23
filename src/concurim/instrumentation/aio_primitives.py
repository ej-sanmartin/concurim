"""Instrumented asyncio queue, lock and semaphores.

They emit the same events as the threaded versions. The actor of each event
is the asyncio task running it (see ``aio_tasks``), so a blocked ``get`` is
shown as that task waiting, while the other tasks keep running.
"""

from __future__ import annotations

import asyncio
import contextvars
from typing import Any, Literal

from concurim.instrumentation.queue_support import _Envelope, _Op, _unwrap
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)

# Bound once: the ``asyncio`` attributes may be replaced while patched.
_BaseQueue = asyncio.Queue
_BaseLock = asyncio.Lock
_BaseSemaphore = asyncio.Semaphore
_BaseBounded = asyncio.BoundedSemaphore

# The op of the ``get()`` in progress in this task, read by ``_get``.
_GET_OP: contextvars.ContextVar[_Op | None] = contextvars.ContextVar(
    "concurim_get_op", default=None
)


def _why(error: BaseException) -> str:
    return (
        "cancelled"
        if isinstance(error, asyncio.CancelledError)
        else ("exception")
    )


class TracedAsyncQueue(_BaseQueue):
    """``asyncio.Queue`` that records puts, gets, task_done and join.

    Args:
        maxsize: Capacity (<= 0 means unbounded).
        name: Display name in the viewer.
    """

    def __init__(self, maxsize: int = 0, *, name: str | None = None) -> None:
        super().__init__(maxsize)
        self._cz_name = name
        rec = active_recorder()
        if rec is not None:
            self._cz_rid(rec)

    def _cz_rid(self, rec: Recorder) -> str:
        return rec.resource_id(
            self, "queue", self._cz_name, {"maxsize": self.maxsize}
        )

    def _op(self, rec: Recorder) -> _Op:
        return _Op(rec, self._cz_rid(rec), rec.capture_source())

    # -- hooks, called synchronously by put_nowait / get_nowait -------------

    def _put(self, item: Any) -> None:
        super()._put(item)
        if isinstance(item, _Envelope):
            item.put_event = item.op.emit(
                E.QUEUE_PUT_COMPLETED,
                item.object_id,
                size_after=self.qsize(),
                maxsize=self.maxsize,
            )

    def _get(self) -> Any:
        item = super()._get()
        ctx = _GET_OP.get()
        if ctx is None:
            return item
        if isinstance(item, _Envelope):
            ctx.emit(
                E.QUEUE_GET_COMPLETED,
                item.object_id,
                caused_by=item.put_event,
                size_after=self.qsize(),
            )
        else:  # the item predates the recording
            ctx.emit(
                E.QUEUE_GET_COMPLETED,
                None,
                untracked=True,
                size_after=self.qsize(),
            )
        return item

    # -- public API ---------------------------------------------------------

    def put_nowait(self, item: Any) -> None:
        """``Queue.put_nowait``, recording the attempt."""
        rec = active_recorder()
        if rec is None or isinstance(item, _Envelope):
            return super().put_nowait(item)
        op, oid = self._op(rec), rec.new_object_id()
        op.emit(
            E.QUEUE_PUT_STARTED,
            oid,
            block=False,
            maxsize=self.maxsize,
            **rec.describe_payload(item),
        )
        try:
            super().put_nowait(_Envelope(item, oid, op))
        except asyncio.QueueFull:
            op.emit(E.QUEUE_PUT_FAILED, oid, reason="full")
            raise
        return None

    async def put(self, item: Any) -> None:
        """``Queue.put``; a full queue makes the calling task wait."""
        rec = active_recorder()
        if rec is None:
            return await super().put(item)
        op, oid = self._op(rec), rec.new_object_id()
        op.emit(
            E.QUEUE_PUT_STARTED,
            oid,
            block=True,
            maxsize=self.maxsize,
            **rec.describe_payload(item),
        )
        if self.full():
            op.emit(E.QUEUE_PUT_BLOCKED, oid, reason="full")
        try:
            await super().put(_Envelope(item, oid, op))
        except BaseException as error:
            op.emit(
                E.QUEUE_PUT_FAILED,
                oid,
                reason=_why(error),
                error=type(error).__name__,
            )
            raise
        return None

    def get_nowait(self) -> Any:
        """``Queue.get_nowait``; returns the original object."""
        rec = active_recorder()
        if rec is None:
            return _unwrap(super().get_nowait()).value
        ctx = _GET_OP.get()
        if ctx is not None:  # called by ``get()``, already announced
            return _unwrap(super().get_nowait()).value
        op = self._op(rec)
        op.emit(E.QUEUE_GET_STARTED, None, block=False)
        token = _GET_OP.set(op)
        try:
            return _unwrap(super().get_nowait()).value
        except asyncio.QueueEmpty:
            op.emit(E.QUEUE_GET_FAILED, None, reason="empty")
            raise
        finally:
            _GET_OP.reset(token)

    async def get(self) -> Any:
        """``Queue.get``; an empty queue makes the calling task wait."""
        rec = active_recorder()
        if rec is None:
            return await super().get()
        op = self._op(rec)
        op.emit(E.QUEUE_GET_STARTED, None, block=True)
        if self.empty():
            op.emit(E.QUEUE_GET_BLOCKED, None, reason="empty")
        token = _GET_OP.set(op)
        try:
            return await super().get()
        except BaseException as error:
            op.emit(
                E.QUEUE_GET_FAILED,
                None,
                reason=_why(error),
                error=type(error).__name__,
            )
            raise
        finally:
            _GET_OP.reset(token)

    def task_done(self) -> None:
        """``Queue.task_done``, recorded without claiming which item."""
        rec = active_recorder()
        if rec is None:
            return super().task_done()
        op = self._op(rec)
        first = op.emit(E.QUEUE_TASK_DONE, None)
        try:
            super().task_done()
        except ValueError:
            op.emit(
                E.QUEUE_TASK_DONE_FAILED,
                None,
                caused_by=first,
                reason="called too many times",
            )
            raise
        return None

    async def join(self) -> None:
        """``Queue.join``, recording start and completion."""
        rec = active_recorder()
        if rec is None:
            return await super().join()
        op = self._op(rec)
        op.emit(E.QUEUE_JOIN_STARTED)
        try:
            await super().join()
        except BaseException as error:
            op.emit(E.QUEUE_JOIN_FAILED, None, error=type(error).__name__)
            raise
        op.emit(E.QUEUE_JOIN_COMPLETED)
        return None


class _AsyncHeld:
    """Shared acquire/release recording for asyncio locks and semaphores."""

    _cz_kind = "lock"
    _cz_name: str | None
    _cz_meta: dict[str, Any]

    def _cz_setup(self, kind: str, name: str | None, **meta: Any) -> None:
        self._cz_kind = kind
        self._cz_name = name
        self._cz_meta = {"kind": kind, **meta}
        rec = active_recorder()
        if rec is not None:
            self._cz_rid(rec)

    def _cz_rid(self, rec: Recorder) -> str:
        return rec.resource_id(
            self, self._cz_kind, self._cz_name, self._cz_meta
        )

    async def _cz_acquire(self, rec: Recorder, unavailable: bool, wait: Any):
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        prefix = f"{self._cz_kind}.acquire"
        op.emit(f"{prefix}.started")
        if unavailable:
            op.emit(f"{prefix}.blocked")
        try:
            await wait()
        except BaseException as error:
            op.emit(
                f"{prefix}.failed",
                reason=_why(error),
                error=type(error).__name__,
            )
            raise
        op.emit(f"{prefix}.completed")
        return True

    def _cz_released(self, rec: Recorder) -> None:
        rec.emit(
            f"{self._cz_kind}.released",
            resource_id=self._cz_rid(rec),
            source=rec.capture_source(),
        )


class TracedAsyncLock(_AsyncHeld, _BaseLock):
    """``asyncio.Lock`` that records acquire and release.

    Args:
        name: Display name in the viewer.
    """

    def __init__(self, *, name: str | None = None) -> None:
        super().__init__()
        self._cz_setup("lock", name, value=1)

    async def acquire(self) -> Literal[True]:
        """``Lock.acquire``; a held lock makes the calling task wait."""
        rec = active_recorder()
        if rec is None:
            return await _BaseLock.acquire(self)
        return await self._cz_acquire(
            rec, self.locked(), lambda: _BaseLock.acquire(self)
        )

    def release(self) -> None:
        """``Lock.release``."""
        rec = active_recorder()
        if rec is not None and self.locked():
            self._cz_released(rec)
        _BaseLock.release(self)


class TracedAsyncSemaphore(_AsyncHeld, _BaseSemaphore):
    """``asyncio.Semaphore`` that records acquire and release.

    Args:
        value: Initial number of permits.
        name: Display name in the viewer.
    """

    def __init__(self, value: int = 1, *, name: str | None = None) -> None:
        super().__init__(value)
        self._cz_setup(
            "semaphore",
            name,
            value=value,
            bounded=isinstance(self, _BaseBounded),
        )

    async def acquire(self) -> Literal[True]:
        """``Semaphore.acquire``; no permits makes the task wait."""
        rec = active_recorder()
        if rec is None:
            return await _BaseSemaphore.acquire(self)
        return await self._cz_acquire(
            rec, self.locked(), lambda: _BaseSemaphore.acquire(self)
        )

    def release(self) -> None:
        """``Semaphore.release``."""
        rec = active_recorder()
        initial = getattr(self, "_bound_value", None)
        over = initial is not None and self._value >= initial
        if rec is not None and not over:
            self._cz_released(rec)
        super().release()


class TracedAsyncBoundedSemaphore(TracedAsyncSemaphore, _BaseBounded):
    """``asyncio.BoundedSemaphore`` that records acquire and release."""
