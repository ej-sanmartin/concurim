"""State reconstruction: a deterministic reducer from events to state.

The reducer is the single source of truth for what the viewer shows. It only
uses recorded events; anything that is a guess (for example, which item a
``task_done()`` call finished) is flagged through ``Applied.facts`` so the
explanation layer can label it as inferred.
"""

from __future__ import annotations

from concurim.recorder.events import Event
from concurim.recorder.events import EventType as E
from concurim.replay.models import (
    Applied,
    ObjectState,
    QueueState,
    SyncState,
    ThreadState,
    actor_kind,
)
from concurim.replay.models import (
    resume as _resume,
)
from concurim.replay.state_barrier import BARRIER_HANDLERS
from concurim.replay.state_events import EVENT_HANDLERS
from concurim.replay.state_exec import EXEC_HANDLERS
from concurim.replay.state_sync import SYNC_HANDLERS
from concurim.replay.state_taskgroup import TASKGROUP_HANDLERS

MAX_WARNINGS = 50
MAX_HOLDING = 8  # received-but-unfinished items shown per thread


class Reducer:
    """Applies events in order, mutating the entity dictionaries.

    ``threads`` holds every *actor*: an OS thread or an asyncio task.
    """

    def __init__(self) -> None:
        self.threads: dict[str, ThreadState] = {}
        self.queues: dict[str, QueueState] = {}
        self.syncs: dict[str, SyncState] = {}
        self.objects: dict[str, ObjectState] = {}
        self.warnings: list[str] = []

    def warn(self, text: str) -> None:
        if len(self.warnings) < MAX_WARNINGS and text not in self.warnings:
            self.warnings.append(text)

    # -- entity access ------------------------------------------------------

    def thread(self, ev: Event, app: Applied) -> ThreadState | None:
        actor = ev.actor
        if actor is None:
            return None
        th = self.threads.get(actor)
        if th is None:
            th = self.threads[actor] = ThreadState(
                actor,
                str(ev.metadata.get("name", actor)),
                kind=actor_kind(ev.task_id, ev.metadata),
            )
        app.threads.add(th.id)
        return th

    def sync(self, ev: Event, app: Applied) -> SyncState:
        """The lock or semaphore an event refers to."""
        rid = ev.resource_id or "sync-?"
        s = self.syncs.get(rid)
        if s is None:
            s = self.syncs[rid] = SyncState(rid, rid)
            self.warn(f"{rid} used before its creation event (partial trace)")
        app.syncs.add(rid)
        return s

    def queue(self, ev: Event, app: Applied) -> QueueState:
        rid = ev.resource_id or "queue-?"
        q = self.queues.get(rid)
        if q is None:
            q = self.queues[rid] = QueueState(rid, rid)
            self.warn(f"{rid} used before its creation event (partial trace)")
        app.queues.add(rid)
        return q

    def obj(self, oid: str, app: Applied) -> ObjectState:
        o = self.objects.get(oid)
        if o is None:
            o = self.objects[oid] = ObjectState(oid)
        app.objects.add(oid)
        return o

    # -- reduction ----------------------------------------------------------

    def apply(self, ev: Event) -> Applied:
        app = Applied()
        th = self.thread(ev, app)
        handler = _HANDLERS.get(ev.event_type)
        if handler is None:
            self.warn(f"unknown event type {ev.event_type!r} ignored")
        elif th is not None or ev.actor is None:
            handler(self, ev, app, th)
        return app

    # -- thread events ------------------------------------------------------

    def _thread_registered(self, ev, app, th):
        th.name = str(ev.metadata.get("name", th.name))

    def _thread_started(self, ev, app, th):
        th.name = str(ev.metadata.get("name", th.name))
        th.status, th.basis = "running", "observed"

    def _thread_end(self, ev, app, th):
        th.status = "failed" if ev.event_type == E.THREAD_FAILED else "finished"
        th.basis, th.waiting_on, th.work = "observed", None, None
        app.facts["left_holding"] = len(th.holding)
        held = [
            s.name
            for s in self.syncs.values()
            if s.kind != "semaphore" and th.id in s.holders
        ]
        if held:
            app.facts["left_locked"] = held
        for oid in th.holding:
            self.obj(oid, app).phase = "released"
        th.holding.clear()

    def _work_started(self, ev, app, th):
        th.status, th.basis = "working", "observed"
        th.work = str(ev.metadata.get("name", "work"))
        if ev.object_id:
            self.obj(ev.object_id, app)

    def _work_end(self, ev, app, th):
        th.status, th.basis, th.work = "running", "inferred", None

    def _noop(self, ev, app, th):
        return None

    # -- queue events -------------------------------------------------------

    def _queue_created(self, ev, app, th):
        q = self.queues.setdefault(
            ev.resource_id or "queue-?", QueueState(ev.resource_id or "?", "")
        )
        q.name = str(ev.metadata.get("name", q.id))
        q.maxsize = int(ev.metadata.get("maxsize", 0) or 0)
        app.queues.add(q.id)

    def _derived(self, ev, app, th):
        if ev.object_id:
            self.obj(ev.object_id, app).parent = str(
                ev.metadata.get("parent_object_id")
            )

    def _put_started(self, ev, app, th):
        q = self.queue(ev, app)
        o = self.obj(ev.object_id or "object-?", app)
        o.type = ev.metadata.get("type")
        o.preview = ev.metadata.get("preview")
        o.phase, o.at = "putting", th.id
        app.facts.update(size=len(q.items), maxsize=q.maxsize)

    def _put_blocked(self, ev, app, th):
        q = self.queue(ev, app)
        q.blocked_puts.append(
            {"thread": th.id, "object": ev.object_id, "op": ev.operation_id}
        )
        th.status, th.basis = "waiting", "observed"
        th.waiting_on = {"resource": q.id, "op": "put"}
        app.facts.update(size=len(q.items), maxsize=q.maxsize)

    def _end_wait(self, th: ThreadState, q: QueueState, ev: Event) -> bool:
        before = len(q.blocked_puts) + len(q.blocked_gets)
        q.blocked_puts = [
            b for b in q.blocked_puts if b["op"] != ev.operation_id
        ]
        q.blocked_gets = [
            b for b in q.blocked_gets if b["op"] != ev.operation_id
        ]
        th.waiting_on = None
        _resume(th)
        return before != len(q.blocked_puts) + len(q.blocked_gets)

    def _put_completed(self, ev, app, th):
        q = self.queue(ev, app)
        app.facts["was_blocked"] = self._end_wait(th, q, ev)
        oid = ev.object_id or "object-?"
        q.items.append(oid)
        q.unfinished += 1
        o = self.obj(oid, app)
        o.phase, o.at = "queued", q.id
        app.motion = {"object": oid, "from": th.id, "to": q.id}
        app.facts.update(
            position=len(q.items), maxsize=q.maxsize, unfinished=q.unfinished
        )
        if ev.metadata.get("size_after") != len(q.items):
            self.warn(f"{q.id}: recorded size disagrees with replay")

    def _put_rejected(self, ev, app, th):
        q = self.queue(ev, app)
        self._end_wait(th, q, ev)
        if ev.object_id:
            self.obj(ev.object_id, app).phase = "released"
        app.facts.update(size=len(q.items), maxsize=q.maxsize)

    def _get_blocked(self, ev, app, th):
        q = self.queue(ev, app)
        q.blocked_gets.append({"thread": th.id, "op": ev.operation_id})
        th.status, th.basis = "waiting", "observed"
        th.waiting_on = {"resource": q.id, "op": "get"}

    def _get_completed(self, ev, app, th):
        q = self.queue(ev, app)
        app.facts["was_blocked"] = self._end_wait(th, q, ev)
        oid = ev.object_id
        if q.items and q.items[0] == oid:
            q.items.popleft()  # the FIFO case, O(1)
        elif oid in q.items:
            self.warn(f"{q.id}: item left out of FIFO order")
            q.items.remove(oid)
        elif q.items:
            oid = q.items.popleft()  # untracked item: assume front
        if oid is None:
            return
        th.holding.append(oid)
        while len(th.holding) > MAX_HOLDING:
            # A worker that never calls task_done() would otherwise grow
            # without bound; show only its most recent receipts.
            self.obj(th.holding.pop(0), app).phase = "released"
        o = self.obj(oid, app)
        o.phase, o.at = "held", th.id
        app.motion = {"object": oid, "from": q.id, "to": th.id}
        app.facts.update(
            size=len(q.items),
            maxsize=q.maxsize,
            unfinished=q.unfinished,
            object=oid,
        )

    def _get_rejected(self, ev, app, th):
        self._end_wait(th, self.queue(ev, app), ev)

    def _task_done(self, ev, app, th):
        q = self.queue(ev, app)
        app.facts["unfinished_before"] = q.unfinished
        q.unfinished = max(0, q.unfinished - 1)
        app.facts["unfinished"] = q.unfinished
        oid = ev.object_id
        inferred = oid is None
        if inferred and th.holding:
            oid = th.holding[0]
        if oid in th.holding:
            th.holding.remove(oid)
            self.obj(oid, app).phase = "released"
            app.facts.update(released=oid, released_inferred=inferred)

    def _join_started(self, ev, app, th):
        q = self.queue(ev, app)
        app.facts["unfinished"] = q.unfinished
        if q.unfinished > 0:
            q.joiners.append(th.id)
            th.status, th.basis = "waiting", "observed"
            th.waiting_on = {"resource": q.id, "op": "join"}

    def _join_end(self, ev, app, th):
        q = self.queue(ev, app)
        if th.id in q.joiners:
            q.joiners.remove(th.id)
        th.waiting_on = None
        _resume(th)

    def _shutdown(self, ev, app, th):
        q = self.queue(ev, app)
        q.shutdown = "immediate" if ev.metadata.get("immediate") else "graceful"
        app.facts.update(size=len(q.items), unfinished=q.unfinished)

    def _discarded(self, ev, app, th):
        q = self.queue(ev, app)
        oid = ev.object_id or "object-?"
        if oid in q.items:
            q.items.remove(oid)
        q.unfinished = max(0, q.unfinished - 1)
        self.obj(oid, app).phase = "discarded"
        app.motion = {"object": oid, "from": q.id, "to": None}
        app.facts["unfinished"] = q.unfinished


_HANDLERS = {
    E.THREAD_REGISTERED: Reducer._thread_registered,
    E.THREAD_START_REQUESTED: Reducer._noop,
    E.THREAD_STARTED: Reducer._thread_started,
    E.THREAD_FINISHED: Reducer._thread_end,
    E.THREAD_FAILED: Reducer._thread_end,
    E.WORK_STARTED: Reducer._work_started,
    E.WORK_FINISHED: Reducer._work_end,
    E.WORK_FAILED: Reducer._work_end,
    E.OBJECT_DERIVED: Reducer._derived,
    E.QUEUE_CREATED: Reducer._queue_created,
    E.QUEUE_PUT_STARTED: Reducer._put_started,
    E.QUEUE_PUT_BLOCKED: Reducer._put_blocked,
    E.QUEUE_PUT_COMPLETED: Reducer._put_completed,
    E.QUEUE_PUT_TIMEOUT: Reducer._put_rejected,
    E.QUEUE_PUT_FAILED: Reducer._put_rejected,
    E.QUEUE_GET_STARTED: Reducer._noop,
    E.QUEUE_GET_BLOCKED: Reducer._get_blocked,
    E.QUEUE_GET_COMPLETED: Reducer._get_completed,
    E.QUEUE_GET_TIMEOUT: Reducer._get_rejected,
    E.QUEUE_GET_FAILED: Reducer._get_rejected,
    E.QUEUE_TASK_DONE: Reducer._task_done,
    E.QUEUE_TASK_DONE_FAILED: Reducer._noop,
    E.QUEUE_JOIN_STARTED: Reducer._join_started,
    E.QUEUE_JOIN_COMPLETED: Reducer._join_end,
    E.QUEUE_JOIN_FAILED: Reducer._join_end,
    E.QUEUE_SHUTDOWN_REQUESTED: Reducer._shutdown,
    E.QUEUE_ITEM_DISCARDED: Reducer._discarded,
    **SYNC_HANDLERS,
    **EVENT_HANDLERS,
    **BARRIER_HANDLERS,
    **TASKGROUP_HANDLERS,
    **EXEC_HANDLERS,
}
