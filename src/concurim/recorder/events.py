"""Typed, versioned event model for Concurim traces.

Events are plain frozen dataclasses that round-trip through JSON. Loading
validates every field, so an untrusted trace can never cause more than a
``TraceFormatError``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1
MAX_METADATA_KEYS = 24
MAX_STRING_LEN = 512


class TraceFormatError(ValueError):
    """Raised when a trace or event does not match the documented format."""


class EventType:
    """Names of the events emitted by the built-in instrumentation."""

    THREAD_REGISTERED = "thread.registered"
    THREAD_START_REQUESTED = "thread.start.requested"
    THREAD_STARTED = "thread.started"
    THREAD_FINISHED = "thread.finished"
    THREAD_FAILED = "thread.failed"
    WORK_STARTED = "work.started"
    WORK_FINISHED = "work.finished"
    WORK_FAILED = "work.failed"
    OBJECT_DERIVED = "object.derived"
    QUEUE_CREATED = "queue.created"
    QUEUE_PUT_STARTED = "queue.put.started"
    QUEUE_PUT_BLOCKED = "queue.put.blocked"
    QUEUE_PUT_COMPLETED = "queue.put.completed"
    QUEUE_PUT_TIMEOUT = "queue.put.timeout"
    QUEUE_PUT_FAILED = "queue.put.failed"
    QUEUE_GET_STARTED = "queue.get.started"
    QUEUE_GET_BLOCKED = "queue.get.blocked"
    QUEUE_GET_COMPLETED = "queue.get.completed"
    QUEUE_GET_TIMEOUT = "queue.get.timeout"
    QUEUE_GET_FAILED = "queue.get.failed"
    QUEUE_TASK_DONE = "queue.task_done"
    QUEUE_TASK_DONE_FAILED = "queue.task_done.failed"
    QUEUE_JOIN_STARTED = "queue.join.started"
    QUEUE_JOIN_COMPLETED = "queue.join.completed"
    QUEUE_JOIN_FAILED = "queue.join.failed"
    QUEUE_SHUTDOWN_REQUESTED = "queue.shutdown.requested"
    QUEUE_ITEM_DISCARDED = "queue.item.discarded"
    # Locks and semaphores share one acquire/release lifecycle.
    LOCK_CREATED = "lock.created"
    LOCK_ACQUIRE_STARTED = "lock.acquire.started"
    LOCK_ACQUIRE_BLOCKED = "lock.acquire.blocked"
    LOCK_ACQUIRE_COMPLETED = "lock.acquire.completed"
    LOCK_ACQUIRE_FAILED = "lock.acquire.failed"
    LOCK_RELEASED = "lock.released"
    SEMAPHORE_CREATED = "semaphore.created"
    SEMAPHORE_ACQUIRE_STARTED = "semaphore.acquire.started"
    SEMAPHORE_ACQUIRE_BLOCKED = "semaphore.acquire.blocked"
    SEMAPHORE_ACQUIRE_COMPLETED = "semaphore.acquire.completed"
    SEMAPHORE_ACQUIRE_FAILED = "semaphore.acquire.failed"
    SEMAPHORE_RELEASED = "semaphore.released"
    EXECUTOR_CREATED = "executor.created"
    EXECUTOR_SUBMIT = "executor.submit"
    EXECUTOR_TASK_STARTED = "executor.task.started"
    EXECUTOR_TASK_FINISHED = "executor.task.finished"
    EXECUTOR_TASK_FAILED = "executor.task.failed"
    EXECUTOR_SHUTDOWN = "executor.shutdown"
    TASK_CREATED = "task.created"
    TASK_STEP_STARTED = "task.step.started"
    TASK_STEP_ENDED = "task.step.ended"
    TASK_FINISHED = "task.finished"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    # Sampled, approximate position of a worker (not a state change).
    CODE_SAMPLED = "code.sampled"


@dataclass(frozen=True, slots=True)
class Source:
    """Where in user code an event was triggered."""

    file: str
    line: int
    function: str

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "function": self.function}


@dataclass(frozen=True, slots=True)
class Event:
    """One recorded observation.

    ``sequence`` is the total order within one process. Events from different
    processes are only ordered by explicit ``caused_by`` edges.
    """

    event_id: str
    event_type: str
    timestamp_ns: int
    sequence: int
    process_id: int
    thread_id: str | None = None
    task_id: str | None = None
    resource_id: str | None = None
    object_id: str | None = None
    operation_id: str | None = None
    caused_by: str | None = None
    source: Source | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    @property
    def actor(self) -> str | None:
        """The unit of execution: an asyncio task, else the thread."""
        return self.task_id or self.thread_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict, omitting empty fields."""
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp_ns": self.timestamp_ns,
            "sequence": self.sequence,
            "process_id": self.process_id,
        }
        for key in (
            "thread_id",
            "task_id",
            "resource_id",
            "object_id",
            "operation_id",
            "caused_by",
        ):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        if self.source is not None:
            out["source"] = self.source.to_dict()
        if self.metadata:
            out["metadata"] = self.metadata
        return out

    @classmethod
    def from_dict(cls, data: Any) -> Event:
        """Validate and build an event from untrusted JSON data."""
        if not isinstance(data, dict):
            raise TraceFormatError("event must be a JSON object")
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise TraceFormatError(f"unsupported schema_version: {version!r}")
        kwargs: dict[str, Any] = {}
        for key in ("event_id", "event_type"):
            kwargs[key] = _req_str(data, key)
        for key in ("timestamp_ns", "sequence", "process_id"):
            kwargs[key] = _req_int(data, key)
        for key in (
            "thread_id",
            "task_id",
            "resource_id",
            "object_id",
            "operation_id",
            "caused_by",
        ):
            kwargs[key] = _opt_str(data, key)
        kwargs["source"] = _parse_source(data.get("source"))
        kwargs["metadata"] = _parse_metadata(data.get("metadata"))
        return cls(**kwargs)


def _req_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or len(value) > MAX_STRING_LEN:
        raise TraceFormatError(f"{key} must be a string")
    return value


def _opt_str(data: dict[str, Any], key: str) -> str | None:
    if data.get(key) is None:
        return None
    return _req_str(data, key)


def _req_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TraceFormatError(f"{key} must be an integer")
    return value


def _parse_source(raw: Any) -> Source | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise TraceFormatError("source must be an object")
    return Source(
        _req_str(raw, "file"), _req_int(raw, "line"), _req_str(raw, "function")
    )


def _parse_metadata(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict) or len(raw) > MAX_METADATA_KEYS:
        raise TraceFormatError("metadata must be a small object")
    for key, value in raw.items():
        ok = value is None or isinstance(value, (bool, int, float, str))
        if not ok or (isinstance(value, str) and len(value) > MAX_STRING_LEN):
            raise TraceFormatError(f"metadata[{key!r}] must be a scalar")
    return dict(raw)
