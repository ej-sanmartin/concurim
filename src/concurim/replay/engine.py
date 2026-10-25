"""Build the replay model consumed by the viewer.

``build_replay`` turns a loaded trace into one JSON-serializable document:
the normalized events plus one *frame* per event. A frame lists the entity
states that event changed, so the viewer can reach any event by folding
frames (and keep per-event snapshots with structural sharing). The same trace
always yields the same document.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from concurim.recorder.events import Event
from concurim.recorder.events import EventType as E
from concurim.recorder.serialization import Trace
from concurim.replay.code_view import function_ranges, split_line_samples
from concurim.replay.explanations import explain
from concurim.replay.models import Applied, snapshot
from concurim.replay.state import Reducer

REPLAY_VERSION = 1

# event type -> (span kind, is_opening)
_SPAN_OPEN = {
    E.QUEUE_PUT_BLOCKED: "wait_put",
    E.QUEUE_GET_BLOCKED: "wait_get",
    E.WORK_STARTED: "work",
    E.EXECUTOR_TASK_STARTED: "work",
    E.LOCK_ACQUIRE_BLOCKED: "wait_lock",
    E.SEMAPHORE_ACQUIRE_BLOCKED: "wait_lock",
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
}


def build_replay(trace: Trace) -> dict[str, Any]:
    """Reconstruct state for every event of ``trace``.

    Returns:
        A JSON-serializable dict with ``metadata``, ``events``, ``frames``,
        ``entities``, ``spans``, ``occupancy``, ``summary`` and ``warnings``.
    """
    events, samples = split_line_samples(trace.events)
    red = Reducer()
    frames: list[dict[str, Any]] = []
    spans: list[dict[str, Any]] = []
    open_spans: dict[str, dict[str, Any]] = {}
    occupancy: dict[str, list[list[int]]] = {}
    journeys: dict[str, list[list[Any]]] = {}
    holds: dict[tuple[str, str], dict[str, Any]] = {}
    last_index = max(len(events) - 1, 0)

    for i, ev in enumerate(events):
        before = {
            q: (len(s.items), s.unfinished) for q, s in red.queues.items()
        }
        app = red.apply(ev)
        frames.append(
            {
                "i": i,
                "changes": _snapshot(red, app),
                "explanation": explain(ev, red, app),
                "motion": app.motion,
            }
        )
        _track_spans(i, ev, app, spans, open_spans)
        _track_occupancy(i, red, app, before, occupancy)
        _track_journeys(i, red, app, journeys)
        _track_holds(i, ev, app, spans, holds)

    for span in [*open_spans.values(), *holds.values()]:
        span.pop("depth", None)
        span.update(end=last_index, outcome="open")
        spans.append(span)
    spans.sort(key=lambda s: (s["start"], s["end"]))

    warnings = list(red.warnings)
    if trace.metadata.get("truncated"):
        warnings.insert(
            0,
            f"Trace is truncated: "
            f"{trace.metadata.get('dropped_events', '?')} events "
            "were dropped after the buffer limit was reached.",
        )
    if trace.metadata.get("samples_truncated"):
        warnings.append(
            "Line sampling hit its limit: the code view is stale after that."
        )
    return {
        "replay_version": REPLAY_VERSION,
        "metadata": {k: v for k, v in trace.metadata.items() if k != "sources"},
        "source_paths": sorted(trace.sources),
        "events": [e.to_dict() for e in events],
        "line_samples": samples,
        "code_ranges": function_ranges(trace.sources),
        "frames": frames,
        "entities": _entities(red, events, journeys),
        "spans": spans,
        "occupancy": occupancy,
        "summary": _summary(events),
        "warnings": warnings,
    }


def _snapshot(red: Reducer, app: Applied) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if app.threads:
        changes["threads"] = {
            t: snapshot(red.threads[t]) for t in sorted(app.threads)
        }
    if app.queues:
        changes["queues"] = {
            q: snapshot(red.queues[q]) for q in sorted(app.queues)
        }
    if app.syncs:
        changes["syncs"] = {
            s: snapshot(red.syncs[s]) for s in sorted(app.syncs)
        }
    if app.objects:
        changes["objects"] = {
            o: snapshot(red.objects[o]) for o in sorted(app.objects)
        }
    return changes


def _track_spans(
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
        span.update(end=i, outcome=outcome)
        spans.append(span)


def _track_holds(
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


def _track_occupancy(
    i: int,
    red: Reducer,
    app: Applied,
    before: dict[str, tuple[int, int]],
    occupancy: dict[str, list[list[int]]],
) -> None:
    for qid in app.queues:
        q = red.queues[qid]
        now = (len(q.items), q.unfinished)
        if before.get(qid) != now:
            occupancy.setdefault(qid, []).append([i, *now])


def _track_journeys(
    i: int, red: Reducer, app: Applied, journeys: dict[str, list[list[Any]]]
) -> None:
    for oid in app.objects:
        o = red.objects[oid]
        if o.phase == "new":
            continue
        trail = journeys.setdefault(oid, [])
        step = [i, o.phase, o.at]
        if not trail or trail[-1][1:] != step[1:]:
            trail.append(step)


def _entities(
    red: Reducer, events: list[Event], journeys: dict[str, list[list[Any]]]
) -> dict[str, Any]:
    first: dict[str, int] = {}
    last: dict[str, int] = {}
    for i, ev in enumerate(events):
        if ev.actor:
            first.setdefault(ev.actor, i)
            last[ev.actor] = i
    return {
        "threads": {
            t.id: {
                "id": t.id,
                "name": t.name,
                "kind": t.kind,
                "first": first.get(t.id, 0),
                "last": last.get(t.id, 0),
            }
            for t in red.threads.values()
        },
        "queues": {
            q.id: {
                "id": q.id,
                "name": q.name,
                "maxsize": q.maxsize,
                "kind": q.kind,
                "workers": q.workers,
            }
            for q in red.queues.values()
        },
        "syncs": {
            s.id: {
                "id": s.id,
                "name": s.name,
                "kind": s.kind,
                "capacity": s.capacity,
            }
            for s in red.syncs.values()
        },
        "objects": {
            o.id: {
                "id": o.id,
                "type": o.type,
                "preview": o.preview,
                "parent": o.parent,
                "journey": journeys.get(o.id, []),
            }
            for o in red.objects.values()
        },
    }


def _summary(events: list[Event]) -> dict[str, Any]:
    counts = Counter(e.event_type for e in events)
    return {
        "event_count": len(events),
        "duration_ns": events[-1].timestamp_ns if events else 0,
        "by_type": dict(sorted(counts.items())),
    }
