"""Instrumented ``queue.Queue``.

``TracedQueue`` is a real ``queue.Queue`` subclass. Only ``put``, ``get``,
``task_done``, ``join`` and ``shutdown`` are wrapped; ``put_nowait`` and
``get_nowait`` delegate to them inside the standard library, so each logical
operation is recorded once.

Ordering guarantee: the events that change queue contents
(``queue.put.completed``, ``queue.get.completed``, ``queue.item.discarded``)
are emitted from the ``_put``/``_get`` hooks, which the standard library calls
while holding the queue's mutex. Their sequence numbers therefore match the
true order of queue mutations. "Started", "blocked", "timeout" and "failed"
events are emitted outside the mutex and describe what the caller observed.

Items are stored in a private envelope carrying a logical ``object_id``;
consumers still receive the original object.
"""

from __future__ import annotations

import queue
import threading
from typing import Any

from concurim.instrumentation.queue_support import (
    QueueItem,
    _Envelope,
    _Op,
    _unwrap,
    run_two_phase,
)
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)
mark_internal(queue.__file__)

_NEG_TIMEOUT = "'timeout' must be a non-negative number"


class TracedQueue(queue.Queue):
    """Drop-in ``queue.Queue`` that records its operations.

    Outside a ``concurim.record()`` block it behaves exactly like
    ``queue.Queue``. Start recording *before* creating the queue and putting
    items so the replay sees the full history.

    Args:
        maxsize: Capacity (<= 0 means unbounded), as for ``queue.Queue``.
        name: Display name in the viewer.
    """

    def __init__(self, maxsize: int = 0, *, name: str | None = None) -> None:
        self._cz_name = name
        self._cz_tls = threading.local()
        super().__init__(maxsize)
        rec = active_recorder()
        if rec is not None:
            self._cz_rid(rec)

    def _cz_rid(self, rec: Recorder) -> str:
        return rec.resource_id(
            self, "queue", self._cz_name, {"maxsize": self.maxsize}
        )

    # -- hooks, called by queue.Queue while holding the mutex ---------------

    def _put(self, item: Any) -> None:
        super()._put(item)
        if isinstance(item, _Envelope):
            # Consumers' causal edge points at this event: it is what made
            # the item available.
            item.put_event = item.op.emit(
                E.QUEUE_PUT_COMPLETED,
                item.object_id,
                size_after=self._qsize(),
                maxsize=self.maxsize,
            )

    def _get(self) -> Any:
        item = super()._get()
        if not isinstance(item, _Envelope):
            ctx = getattr(self._cz_tls, "get_op", None)
            if ctx is not None:  # item predates the recording
                ctx.emit(
                    E.QUEUE_GET_COMPLETED,
                    None,
                    untracked=True,
                    size_after=self._qsize(),
                )
            return item
        if getattr(self._cz_tls, "draining", False):
            item.op.rec.emit(
                E.QUEUE_ITEM_DISCARDED,
                resource_id=item.op.rid,
                object_id=item.object_id,
                caused_by=item.put_event,
                metadata={"size_after": self._qsize()},
            )
            return item
        ctx = getattr(self._cz_tls, "get_op", None)
        if ctx is not None:
            ctx.emit(
                E.QUEUE_GET_COMPLETED,
                item.object_id,
                caused_by=item.put_event,
                size_after=self._qsize(),
            )
        return item

    # -- public API ---------------------------------------------------------

    def put(
        self,
        item: Any,
        block: bool = True,
        timeout: float | None = None,
        *,
        derived_from: str | None = None,
    ) -> None:
        """``queue.Queue.put`` plus optional lineage.

        Args:
            derived_from: ``object_id`` of the item this one was produced
                from; recorded as an explicit lineage edge.
        """
        rec = active_recorder()
        if rec is None:
            return super().put(item, block, timeout)
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        oid = rec.new_object_id()
        if derived_from is not None:
            rec.emit(
                E.OBJECT_DERIVED,
                object_id=oid,
                source=op.source,
                metadata={"parent_object_id": str(derived_from)[:128]},
            )
        op.emit(
            E.QUEUE_PUT_STARTED,
            oid,
            block=block,
            timeout=timeout,
            maxsize=self.maxsize,
            **rec.describe_payload(item),
        )
        env = _Envelope(item, oid, op)
        if block and timeout is not None and timeout < 0 and self.maxsize > 0:
            op.emit(E.QUEUE_PUT_FAILED, oid, reason="invalid_timeout")
            raise ValueError(_NEG_TIMEOUT)
        run_two_phase(
            op,
            "put",
            queue.Full,
            oid,
            block,
            timeout,
            lambda: queue.Queue.put(self, env, False),
            lambda t: queue.Queue.put(self, env, True, t),
        )
        return None

    def get(self, block: bool = True, timeout: float | None = None) -> Any:
        """``queue.Queue.get``; returns the original object."""
        return self._get_tracked(block, timeout).value

    def get_with_id(
        self, block: bool = True, timeout: float | None = None
    ) -> QueueItem:
        """Like ``get`` but also returns the item's logical ``object_id``."""
        return self._get_tracked(block, timeout)

    def _get_tracked(self, block: bool, timeout: float | None) -> QueueItem:
        rec = active_recorder()
        if rec is None:
            return _unwrap(super().get(block, timeout))
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        op.emit(E.QUEUE_GET_STARTED, None, block=block, timeout=timeout)
        if block and timeout is not None and timeout < 0:
            op.emit(E.QUEUE_GET_FAILED, None, reason="invalid_timeout")
            raise ValueError(_NEG_TIMEOUT)
        tls = self._cz_tls
        tls.get_op = op
        try:
            raw = run_two_phase(
                op,
                "get",
                queue.Empty,
                None,
                block,
                timeout,
                lambda: queue.Queue.get(self, False),
                lambda t: queue.Queue.get(self, True, t),
            )
        finally:
            tls.get_op = None
        return _unwrap(raw)

    def task_done(self, object_id: str | None = None) -> None:
        """``queue.Queue.task_done`` plus optional explicit item identity.

        Without ``object_id`` the event does not claim which item finished,
        because the standard library does not say.
        """
        rec = active_recorder()
        if rec is None:
            return super().task_done()
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        # Emitted *before* the call: task_done() may wake a join() waiter,
        # whose "completed" event must not precede this one.
        first = op.emit(E.QUEUE_TASK_DONE, object_id)
        try:
            super().task_done()
        except ValueError:
            op.emit(
                E.QUEUE_TASK_DONE_FAILED,
                object_id,
                caused_by=first,
                reason="called too many times",
            )
            raise
        return None

    def join(self) -> None:
        """``queue.Queue.join``, recording start and completion."""
        rec = active_recorder()
        if rec is None:
            return super().join()
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        op.emit(E.QUEUE_JOIN_STARTED)
        try:
            super().join()
        except BaseException as error:
            op.emit(E.QUEUE_JOIN_FAILED, None, error=type(error).__name__)
            raise
        op.emit(E.QUEUE_JOIN_COMPLETED)
        return None

    def shutdown(self, immediate: bool = False) -> None:
        """``queue.Queue.shutdown``. Discarded items are recorded too."""
        rec = active_recorder()
        if rec is None:
            return super().shutdown(immediate)
        op = _Op(rec, self._cz_rid(rec), rec.capture_source())
        # Emitted before the flag flips so woken threads' events follow it.
        op.emit(E.QUEUE_SHUTDOWN_REQUESTED, None, immediate=immediate)
        tls = self._cz_tls
        tls.draining = True
        try:
            super().shutdown(immediate)
        finally:
            tls.draining = False
        return None
