"""Helper types for :mod:`concurim.instrumentation.queues`."""

from __future__ import annotations

import queue
import time
from collections.abc import Callable
from typing import Any, NamedTuple

from concurim.recorder.collector import Recorder, mark_internal

mark_internal(__file__)


class QueueItem(NamedTuple):
    """A dequeued value plus its logical object id (``None`` if untracked)."""

    object_id: str | None
    value: Any


class _Op:
    """Context shared by the events of one put/get call."""

    __slots__ = ("rec", "rid", "op_id", "source")

    def __init__(self, rec: Recorder, rid: str, source: Any) -> None:
        self.rec = rec
        self.rid = rid
        self.op_id = rec.new_operation_id()
        self.source = source

    def emit(
        self,
        event_type: str,
        object_id: str | None = None,
        caused_by: str | None = None,
        **meta: Any,
    ) -> str | None:
        return self.rec.emit(
            event_type,
            resource_id=self.rid,
            object_id=object_id,
            operation_id=self.op_id,
            caused_by=caused_by,
            source=self.source,
            metadata=meta,
        )


class _Envelope:
    """Internal wrapper stored in the underlying queue while recording."""

    __slots__ = ("value", "object_id", "op", "put_event")

    def __init__(self, value: Any, object_id: str, op: _Op) -> None:
        self.value = value
        self.object_id = object_id
        self.op = op
        self.put_event: str | None = None  # set when the put completes


def _unwrap(raw: Any) -> QueueItem:
    if isinstance(raw, _Envelope):
        return QueueItem(raw.object_id, raw.value)
    return QueueItem(None, raw)


def run_two_phase(
    op: _Op,
    kind: str,
    exc: type[Exception],
    oid: str | None,
    block: bool,
    timeout: float | None,
    fast: Callable[[], Any],
    slow: Callable[[float | None], Any],
) -> Any:
    """Try without blocking; if that fails, record and block.

    ``blocked`` therefore means "the queue was full/empty when this call
    first tried", which is exactly what the caller observed.
    """
    reason = "full" if kind == "put" else "empty"
    prefix = f"queue.{kind}"
    try:
        try:
            return fast()
        except exc:
            if not block:
                op.emit(f"{prefix}.failed", oid, reason=reason)
                raise
            op.emit(f"{prefix}.blocked", oid, reason=reason)
            deadline = None if timeout is None else time.monotonic() + timeout
            try:
                remaining = (
                    None
                    if deadline is None
                    else max(0.0, deadline - time.monotonic())
                )
                return slow(remaining)
            except exc:
                op.emit(f"{prefix}.timeout", oid, timeout=timeout)
                raise
    except queue.ShutDown:
        op.emit(f"{prefix}.failed", oid, reason="shutdown")
        raise
    except exc:
        raise
    except BaseException as error:
        op.emit(
            f"{prefix}.failed",
            oid,
            reason="exception",
            error=type(error).__name__,
        )
        raise
