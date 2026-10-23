"""Rule-based, offline explanations for each event.

Every sentence is derived from the recorded event and the reducer's facts.
Statements that rely on inference are returned separately in ``inferred`` so
the viewer can label them honestly. No LLM or network access is involved.
"""

from __future__ import annotations

from typing import Any

from concurim.recorder.events import Event
from concurim.recorder.events import EventType as E
from concurim.replay import rules_queues, rules_threads
from concurim.replay.state import Applied, Reducer


def explain(ev: Event, red: Reducer, app: Applied) -> dict[str, Any]:
    """Return ``{title, text, tone, inferred}`` for one applied event."""
    ctx = _Names(ev, red)
    rule = _RULES.get(ev.event_type)
    if rule is None:
        title, text, tone = ev.event_type, "Event not recognised.", "info"
    else:
        title, text, tone = rule(ctx, ev, app.facts)
    inferred: list[str] = []
    if app.facts.get("released_inferred") and app.facts.get("released"):
        inferred.append(
            f"Which item finished is inferred: {ctx.obj(app.facts['released'])}"
            " is the oldest item this thread received and has not finished."
        )
    return {"title": title, "text": text, "tone": tone, "inferred": inferred}


class _Names:
    """Display names for the entities an event refers to."""

    def __init__(self, ev: Event, red: Reducer) -> None:
        self.red = red
        th = red.threads.get(ev.thread_id or "")
        self.t = th.name if th else (ev.thread_id or "A thread")
        q = red.queues.get(ev.resource_id or "")
        self.q = q.name if q else (ev.resource_id or "the queue")
        self.o = self.obj(ev.object_id)

    def obj(self, oid: str | None) -> str:
        if not oid:
            return "an untracked item"
        o = self.red.objects.get(oid)
        if o is not None and o.preview is not None:
            return f"{oid} ({o.preview!r})"
        return oid


_RULES = {
    E.THREAD_REGISTERED: rules_threads._thread_registered,
    E.THREAD_START_REQUESTED: rules_threads._start_requested,
    E.THREAD_STARTED: rules_threads._thread_started,
    E.THREAD_FINISHED: rules_threads._thread_finished,
    E.THREAD_FAILED: rules_threads._thread_failed,
    E.WORK_STARTED: rules_threads._work_started,
    E.WORK_FINISHED: rules_threads._work_finished,
    E.WORK_FAILED: rules_threads._work_failed,
    E.OBJECT_DERIVED: rules_threads._derived,
    E.QUEUE_CREATED: rules_queues._created,
    E.QUEUE_PUT_STARTED: rules_queues._put_started,
    E.QUEUE_PUT_BLOCKED: rules_queues._put_blocked,
    E.QUEUE_PUT_COMPLETED: rules_queues._put_completed,
    E.QUEUE_PUT_TIMEOUT: rules_queues._put_timeout,
    E.QUEUE_PUT_FAILED: rules_queues._put_failed,
    E.QUEUE_GET_STARTED: rules_queues._get_started,
    E.QUEUE_GET_BLOCKED: rules_queues._get_blocked,
    E.QUEUE_GET_COMPLETED: rules_queues._get_completed,
    E.QUEUE_GET_TIMEOUT: rules_queues._get_timeout,
    E.QUEUE_GET_FAILED: rules_queues._get_failed,
    E.QUEUE_TASK_DONE: rules_queues._task_done,
    E.QUEUE_TASK_DONE_FAILED: rules_queues._task_done_failed,
    E.QUEUE_JOIN_STARTED: rules_queues._join_started,
    E.QUEUE_JOIN_COMPLETED: rules_queues._join_completed,
    E.QUEUE_JOIN_FAILED: rules_queues._join_failed,
    E.QUEUE_SHUTDOWN_REQUESTED: rules_queues._shutdown,
    E.QUEUE_ITEM_DISCARDED: rules_queues._discarded,
}
