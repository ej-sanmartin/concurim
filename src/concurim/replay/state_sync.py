"""Reducer handlers for locks and semaphores.

Handlers have the signature ``(reducer, event, applied, actor)`` and are
registered into the reducer's dispatch table.
"""

from __future__ import annotations

from typing import Any

from concurim.replay.models import SyncState, resume


def _created(red: Any, ev, app, th):
    rid = ev.resource_id or "sync-?"
    s = red.syncs.setdefault(rid, SyncState(rid, ""))
    s.name = str(ev.metadata.get("name", s.id))
    s.kind = str(ev.metadata.get("kind", "lock"))
    s.capacity = int(ev.metadata.get("value", 1) or 0)
    s.value = s.capacity
    app.syncs.add(s.id)


def _blocked(red: Any, ev, app, th):
    s = red.sync(ev, app)
    s.waiters.append({"thread": th.id, "op": ev.operation_id})
    th.status, th.basis = "waiting", "observed"
    th.waiting_on = {"resource": s.id, "op": "acquire"}
    app.facts.update(holders=list(s.holders), value=s.value)


def _end_wait(s, th, ev) -> bool:
    before = len(s.waiters)
    s.waiters = [w for w in s.waiters if w["op"] != ev.operation_id]
    th.waiting_on = None
    resume(th)
    return before != len(s.waiters)


def _completed(red: Any, ev, app, th):
    s = red.sync(ev, app)
    app.facts["was_blocked"] = _end_wait(s, th, ev)
    app.facts["held_by_others"] = list(s.holders)
    s.holders.append(th.id)
    s.value = max(0, s.value - 1)
    app.facts.update(acquired=th.id, value=s.value)


def _failed(red: Any, ev, app, th):
    s = red.sync(ev, app)
    _end_wait(s, th, ev)
    app.facts.update(holders=list(s.holders), value=s.value)


def _released(red: Any, ev, app, th):
    s = red.sync(ev, app)
    count = max(1, int(ev.metadata.get("count", 1) or 1))
    removed: list[str] = []
    for _ in range(count):
        if th.id in s.holders:
            s.holders.remove(th.id)
            removed.append(th.id)
        elif s.holders and s.kind != "semaphore":
            removed.append(s.holders.pop(0))  # released by another actor
    s.value += count
    app.facts.update(
        released_holder=removed[0] if removed else None,
        released_by_other=bool(removed) and removed[0] != th.id,
        count=count,
        value=s.value,
        remaining=len(s.holders),
    )


def _noop(red: Any, ev, app, th):
    red.sync(ev, app)


SYNC_HANDLERS: dict[str, Any] = {}
for _kind in ("lock", "semaphore"):
    SYNC_HANDLERS[f"{_kind}.created"] = _created
    SYNC_HANDLERS[f"{_kind}.acquire.started"] = _noop
    SYNC_HANDLERS[f"{_kind}.acquire.blocked"] = _blocked
    SYNC_HANDLERS[f"{_kind}.acquire.completed"] = _completed
    SYNC_HANDLERS[f"{_kind}.acquire.failed"] = _failed
    SYNC_HANDLERS[f"{_kind}.released"] = _released
