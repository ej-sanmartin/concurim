"""Reducer handlers for barriers.

Handlers have the signature ``(reducer, event, applied, actor)``. Waiters
are arrivals that blocked (``wait.blocked``). The last arrival does not
block, so it is not in that list. ``broken`` follows the flag recorded on
the failing wait: abort leaves it set, reset clears it before the waiters
wake.
"""

from __future__ import annotations

from typing import Any

from concurim.recorder.events import EventType as E
from concurim.replay.models import SyncState
from concurim.replay.state_sync import _end_wait


def _created(red: Any, ev, app, th):
    rid = ev.resource_id or "barrier-?"
    s = red.syncs.setdefault(rid, SyncState(rid, ""))
    s.name = str(ev.metadata.get("name", rid))
    s.kind = "barrier"
    s.capacity = int(ev.metadata.get("parties", 0) or 0)
    s.broken = False
    app.syncs.add(rid)


def _blocked(red: Any, ev, app, th):
    s = red.sync(ev, app)
    s.waiters.append({"thread": th.id, "op": ev.operation_id})
    th.status, th.basis = "waiting", "observed"
    th.waiting_on = {"resource": s.id, "op": "wait"}
    app.facts.update(waiting=len(s.waiters), parties=s.capacity)


def _completed(red: Any, ev, app, th):
    s = red.sync(ev, app)
    app.facts["was_blocked"] = _end_wait(s, th, ev)
    app.facts.update(
        index=ev.metadata.get("index"),
        parties=s.capacity,
        waiting=len(s.waiters),
    )


def _failed(red: Any, ev, app, th):
    s = red.sync(ev, app)
    app.facts["was_blocked"] = _end_wait(s, th, ev)
    if "broken" in ev.metadata:
        s.broken = bool(ev.metadata["broken"])
    app.facts.update(waiting=len(s.waiters), reason=ev.metadata.get("reason"))


def _abort(red: Any, ev, app, th):
    s = red.sync(ev, app)
    s.broken = True
    app.facts.update(waiting=len(s.waiters), parties=s.capacity, who=th.id)


def _reset(red: Any, ev, app, th):
    s = red.sync(ev, app)
    s.broken = False
    app.facts.update(waiting=len(s.waiters), parties=s.capacity, who=th.id)


def _noop(red: Any, ev, app, th):
    red.sync(ev, app)


BARRIER_HANDLERS: dict[str, Any] = {
    E.BARRIER_CREATED: _created,
    E.BARRIER_WAIT_STARTED: _noop,
    E.BARRIER_WAIT_BLOCKED: _blocked,
    E.BARRIER_WAIT_COMPLETED: _completed,
    E.BARRIER_WAIT_FAILED: _failed,
    E.BARRIER_ABORT: _abort,
    E.BARRIER_RESET: _reset,
}
