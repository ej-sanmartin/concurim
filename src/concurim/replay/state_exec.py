"""Reducer handlers for executors and asyncio tasks.

An executor is modelled as a ``QueueState`` of kind ``"executor"``: pending
tasks wait in it, and workers take them, so the same queue visuals apply.
Handlers have the signature ``(reducer, event, applied, actor)``.
"""

from __future__ import annotations

from typing import Any

from concurim.recorder.events import EventType as E
from concurim.replay.models import QueueState, ThreadState, resume

# -- executors ---------------------------------------------------------------


def _created(red: Any, ev, app, th):
    rid = ev.resource_id or "executor-?"
    q = red.queues.setdefault(rid, QueueState(rid, ""))
    q.name = str(ev.metadata.get("name", rid))
    q.kind = "executor"
    q.workers = int(ev.metadata.get("max_workers", 0) or 0)
    app.queues.add(rid)


def _submit(red: Any, ev, app, th):
    q = red.queue(ev, app)
    oid = ev.object_id or "task-?"
    q.items.append(oid)
    q.unfinished += 1
    o = red.obj(oid, app)
    o.type = "task"
    o.preview = ev.metadata.get("name")
    o.phase, o.at = "queued", q.id
    app.motion = {"object": oid, "from": th.id, "to": q.id}
    app.facts.update(
        position=len(q.items), unfinished=q.unfinished, running=q.running
    )


def _started(red: Any, ev, app, th):
    q = red.queue(ev, app)
    oid = ev.object_id or "task-?"
    if q.items and q.items[0] == oid:
        q.items.popleft()
    elif oid in q.items:
        q.items.remove(oid)
    q.running += 1
    th.holding.append(oid)
    th.status, th.basis = "working", "observed"
    th.work = str(ev.metadata.get("name", "task"))
    o = red.obj(oid, app)
    o.phase, o.at = "held", th.id
    app.motion = {"object": oid, "from": q.id, "to": th.id}
    app.facts.update(
        pending=len(q.items), running=q.running, unfinished=q.unfinished
    )


def _ended(red: Any, ev, app, th):
    q = red.queue(ev, app)
    oid = ev.object_id or "task-?"
    q.running = max(0, q.running - 1)
    q.unfinished = max(0, q.unfinished - 1)
    if oid in th.holding:
        th.holding.remove(oid)
    red.obj(oid, app).phase = "released"
    th.work = None
    resume(th)
    app.facts.update(
        pending=len(q.items), running=q.running, unfinished=q.unfinished
    )


def _shutdown(red: Any, ev, app, th):
    q = red.queue(ev, app)
    cancel = bool(ev.metadata.get("cancel_futures"))
    q.shutdown = "immediate" if cancel else "graceful"
    dropped = list(q.items) if cancel else []
    for oid in dropped:
        red.obj(oid, app).phase = "discarded"
        q.unfinished = max(0, q.unfinished - 1)
    if cancel:
        q.items.clear()
    app.facts.update(
        dropped=len(dropped), pending=len(q.items), running=q.running
    )


# -- asyncio tasks -----------------------------------------------------------


def _task_created(red: Any, ev, app, th):
    child = str(ev.metadata.get("child", ""))
    if not child:
        return
    state = red.threads.get(child)
    if state is None:
        state = red.threads[child] = ThreadState(
            child, str(ev.metadata.get("name", child)), kind="task"
        )
    state.name = str(ev.metadata.get("name", state.name))
    state.status, state.basis = "suspended", "observed"
    app.threads.add(child)


def _step_started(red: Any, ev, app, th):
    th.status, th.basis = "running", "observed"
    th.waiting_on = None


def _step_ended(red: Any, ev, app, th):
    if ev.metadata.get("done"):
        return
    th.status = "waiting" if th.waiting_on else "suspended"
    th.basis = "observed"


def _task_end(red: Any, ev, app, th):
    th.status = {
        E.TASK_FAILED: "failed",
        E.TASK_CANCELLED: "cancelled",
    }.get(ev.event_type, "finished")
    th.basis, th.waiting_on, th.work = "observed", None, None
    for oid in th.holding:
        red.obj(oid, app).phase = "released"
    app.facts["left_holding"] = len(th.holding)
    th.holding.clear()


EXEC_HANDLERS = {
    E.EXECUTOR_CREATED: _created,
    E.EXECUTOR_SUBMIT: _submit,
    E.EXECUTOR_TASK_STARTED: _started,
    E.EXECUTOR_TASK_FINISHED: _ended,
    E.EXECUTOR_TASK_FAILED: _ended,
    E.EXECUTOR_SHUTDOWN: _shutdown,
    E.TASK_CREATED: _task_created,
    E.TASK_STEP_STARTED: _step_started,
    E.TASK_STEP_ENDED: _step_ended,
    E.TASK_FINISHED: _task_end,
    E.TASK_FAILED: _task_end,
    E.TASK_CANCELLED: _task_end,
}
