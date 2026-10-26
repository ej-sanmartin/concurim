"""Reducer handlers for events and conditions.

They live in ``SyncState`` next to locks, so the same node, waiter list and
timeline spans apply. Handlers have the signature
``(reducer, event, applied, actor)``.

An event's waiters are only those that found it unset (``wait.blocked``). A
condition's waiters are everyone between ``wait.started`` and the end of the
wait; ``notified`` counts signals not yet matched by a resumed waiter. The
notifier never says *which* waiter wakes, so neither does the state.
"""

from __future__ import annotations

from typing import Any

from concurim.recorder.events import EventType as E
from concurim.replay.models import SyncState
from concurim.replay.state_sync import _end_wait


def _event_created(red: Any, ev, app, th):
    rid = ev.resource_id or "event-?"
    s = red.syncs.setdefault(rid, SyncState(rid, ""))
    s.name = str(ev.metadata.get("name", rid))
    s.kind = "event"
    s.is_set = bool(ev.metadata.get("is_set", False))
    app.syncs.add(rid)


def _event_set(red: Any, ev, app, th):
    s = red.sync(ev, app)
    app.facts.update(already_set=s.is_set, waiting=len(s.waiters), who=th.id)
    s.is_set = True


def _event_cleared(red: Any, ev, app, th):
    s = red.sync(ev, app)
    app.facts["was_set"] = s.is_set
    s.is_set = False


def _wait_blocked(red: Any, ev, app, th):
    s = red.sync(ev, app)
    s.waiters.append({"thread": th.id, "op": ev.operation_id})
    th.status, th.basis = "waiting", "observed"
    th.waiting_on = {"resource": s.id, "op": "wait"}
    app.facts.update(is_set=s.is_set, waiting=len(s.waiters))


def _wait_end(red: Any, ev, app, th):
    s = red.sync(ev, app)
    app.facts["was_blocked"] = _end_wait(s, th, ev)
    if s.kind == "condition" and ev.event_type == E.CONDITION_WAIT_COMPLETED:
        s.notified = max(0, s.notified - 1)
    app.facts.update(is_set=s.is_set, waiting=len(s.waiters))


def _noop(red: Any, ev, app, th):
    red.sync(ev, app)


def _condition_created(red: Any, ev, app, th):
    rid = ev.resource_id or "condition-?"
    s = red.syncs.setdefault(rid, SyncState(rid, ""))
    s.name = str(ev.metadata.get("name", rid))
    s.kind = "condition"
    s.lock = ev.metadata.get("lock") or None
    app.syncs.add(rid)


def _cond_wait_started(red: Any, ev, app, th):
    s = red.sync(ev, app)
    s.waiters.append({"thread": th.id, "op": ev.operation_id})
    th.status, th.basis = "waiting", "observed"
    th.waiting_on = {"resource": s.id, "op": "wait"}
    app.facts.update(waiting=len(s.waiters), lock=s.lock)


def _notify(red: Any, ev, app, th):
    s = red.sync(ev, app)
    woken = int(ev.metadata.get("woken", 0) or 0)
    s.notified = min(len(s.waiters), s.notified + woken)
    app.facts.update(
        woken=woken,
        waiting=len(s.waiters),
        everyone=bool(ev.metadata.get("all")),
        lock=s.lock,
        who=th.id,
    )


EVENT_HANDLERS: dict[str, Any] = {
    E.EVENT_CREATED: _event_created,
    E.EVENT_SET: _event_set,
    E.EVENT_CLEARED: _event_cleared,
    E.EVENT_WAIT_STARTED: _noop,
    E.EVENT_WAIT_BLOCKED: _wait_blocked,
    E.EVENT_WAIT_COMPLETED: _wait_end,
    E.EVENT_WAIT_TIMEOUT: _wait_end,
    E.EVENT_WAIT_FAILED: _wait_end,
    E.CONDITION_CREATED: _condition_created,
    E.CONDITION_NOTIFY: _notify,
    E.CONDITION_WAIT_STARTED: _cond_wait_started,
    E.CONDITION_WAIT_COMPLETED: _wait_end,
    E.CONDITION_WAIT_TIMEOUT: _wait_end,
    E.CONDITION_WAIT_FAILED: _wait_end,
}
