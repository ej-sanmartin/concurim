"""Reducer handlers for ``asyncio.TaskGroup``.

A group is a ``SyncState`` of kind ``"taskgroup"``: ``members`` are the
tasks created through it and ``running`` counts those not finished yet
(decremented by ``task_finished`` when a member task ends). The task that
reaches the end of the ``async with`` block is shown waiting on the group.
"""

from __future__ import annotations

from typing import Any

from concurim.recorder.events import EventType as E
from concurim.replay.models import SyncState
from concurim.replay.state_sync import _end_wait


def _created(red: Any, ev, app, th):
    rid = ev.resource_id or "taskgroup-?"
    s = red.syncs.setdefault(rid, SyncState(rid, ""))
    s.name = str(ev.metadata.get("name", rid))
    s.kind = "taskgroup"
    s.capacity = 0
    app.syncs.add(rid)


def _task_added(red: Any, ev, app, th):
    s = red.sync(ev, app)
    child = str(ev.metadata.get("child", ""))
    if child:
        s.members.append(child)
        s.running += 1
    app.facts.update(
        child=child, name=ev.metadata.get("name"), running=s.running
    )


def _exit_started(red: Any, ev, app, th):
    s = red.sync(ev, app)
    app.facts.update(
        running=s.running,
        body_error=ev.metadata.get("body_error"),
        members=len(s.members),
    )
    if s.running > 0:
        s.waiters.append({"thread": th.id, "op": ev.operation_id})
        th.status, th.basis = "waiting", "observed"
        th.waiting_on = {"resource": s.id, "op": "join"}


def _exit_completed(red: Any, ev, app, th):
    s = red.sync(ev, app)
    _end_wait(s, th, ev)
    app.facts.update(error=ev.metadata.get("error"), members=len(s.members))


def member_ended(red: Any, actor: str, app: Any) -> None:
    """A task finished, failed or was cancelled: update its group(s)."""
    for s in red.syncs.values():
        if s.kind == "taskgroup" and actor in s.members and s.running > 0:
            s.running -= 1
            app.syncs.add(s.id)


TASKGROUP_HANDLERS: dict[str, Any] = {
    E.TASKGROUP_CREATED: _created,
    E.TASKGROUP_TASK_ADDED: _task_added,
    E.TASKGROUP_EXIT_STARTED: _exit_started,
    E.TASKGROUP_EXIT_COMPLETED: _exit_completed,
}
