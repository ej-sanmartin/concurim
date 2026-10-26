"""Timeline spans: waits, holds and work, derived from event pairs.

``track_spans`` opens a span at a blocking or work-start event and closes it
at the matching end event (same ``operation_id``); ``track_holds`` makes a
span for the time an actor holds a lock.
"""

from __future__ import annotations

from typing import Any

from concurim.recorder.events import Event
from concurim.recorder.events import EventType as E
from concurim.replay.models import Applied

# event type -> (span kind, is_opening)
_SPAN_OPEN = {
    E.QUEUE_PUT_BLOCKED: "wait_put",
    E.QUEUE_GET_BLOCKED: "wait_get",
    E.WORK_STARTED: "work",
    E.EXECUTOR_TASK_STARTED: "work",
    E.LOCK_ACQUIRE_BLOCKED: "wait_lock",
    E.SEMAPHORE_ACQUIRE_BLOCKED: "wait_lock",
    E.EVENT_WAIT_BLOCKED: "wait_event",
    E.CONDITION_WAIT_STARTED: "wait_condition",
    E.TASKGROUP_EXIT_STARTED: "wait_taskgroup",
}
_SPAN_CLOSE = {
    E.QUEUE_PUT_COMPLETED: "completed",
    E.QUEUE_PUT_TIMEOUT: "timeout",
    E.QUEUE_PUT_FAILED: "failed",
    E.QUEUE_GET_COMPLETED: "completed",
    E.QUEUE_GET_TIMEOUT: "timeout",
    E.QUEUE_GET_FAILED: "failed",
    E.QUEUE_JOIN_COMPLETED: "completed",
    E.QUEUE_JOIN_FAILED: "failed",
    E.WORK_FINISHED: "completed",
    E.WORK_FAILED: "failed",
    E.EXECUTOR_TASK_FINISHED: "completed",
    E.EXECUTOR_TASK_FAILED: "failed",
    E.LOCK_ACQUIRE_COMPLETED: "completed",
    E.LOCK_ACQUIRE_FAILED: "failed",
    E.SEMAPHORE_ACQUIRE_COMPLETED: "completed",
    E.SEMAPHORE_ACQUIRE_FAILED: "failed",
    E.EVENT_WAIT_COMPLETED: "completed",
    E.EVENT_WAIT_TIMEOUT: "timeout",
    E.EVENT_WAIT_FAILED: "failed",
    E.CONDITION_WAIT_COMPLETED: "completed",
    E.CONDITION_WAIT_TIMEOUT: "timeout",
    E.CONDITION_WAIT_FAILED: "failed",
    E.TASKGROUP_EXIT_COMPLETED: "completed",
}


def track_spans(
    i: int,
    ev: Event,
    app: Applied,
    spans: list[dict[str, Any]],
    open_spans: dict[str, dict[str, Any]],
) -> None:
    op = ev.operation_id
    if op is None:
        return
    kind = _SPAN_OPEN.get(ev.event_type)
    if (
        kind is None
        and ev.event_type == E.QUEUE_JOIN_STARTED
        and app.facts.get("unfinished")
    ):
        kind = "wait_join"
    if kind is not None:
        open_spans[op] = {
            "kind": kind,
            "thread": ev.actor,
            "resource": ev.resource_id,
            "object": ev.object_id,
            "operation": op,
            "start": i,
            "name": ev.metadata.get("name"),
        }
        return
    outcome = _SPAN_CLOSE.get(ev.event_type)
    if outcome is not None and op in open_spans:
        span = open_spans.pop(op)
        if outcome == "completed" and ev.metadata.get("error"):
            outcome = "failed"
        span.update(end=i, outcome=outcome)
        spans.append(span)


def track_holds(
    i: int,
    ev: Event,
    app: Applied,
    spans: list[dict[str, Any]],
    holds: dict[tuple[str, str], dict[str, Any]],
) -> None:
    """Spans for the time an actor holds a lock (first acquire to release)."""
    rid = ev.resource_id or ""
    taken = app.facts.get("acquired")
    if taken:
        key = (rid, taken)
        if key in holds:
            holds[key]["depth"] += 1
        else:
            holds[key] = {
                "kind": "hold",
                "thread": taken,
                "resource": rid,
                "object": None,
                "operation": f"hold-{i}",
                "start": i,
                "name": None,
                "depth": 1,
            }
    freed = app.facts.get("released_holder")
    key = (rid, freed or "")
    if freed and key in holds:
        holds[key]["depth"] -= app.facts.get("count", 1)
        if holds[key]["depth"] <= 0:
            span = holds.pop(key)
            del span["depth"]
            span.update(end=i, outcome="completed")
            spans.append(span)
