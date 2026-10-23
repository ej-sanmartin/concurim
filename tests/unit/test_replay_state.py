"""Reducer/explanation tests on SYNTHETIC event lists (hand-written, not
captures). Real captures are covered by tests/integration."""

from concurim.recorder.events import Event
from concurim.recorder.events import EventType as E
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import world_after as state_after


class Script:
    """Tiny builder for synthetic traces."""

    def __init__(self):
        self.events = []

    def add(self, etype, thread="thread-1", **kw):
        seq = len(self.events) + 1
        meta = kw.pop("metadata", {})
        self.events.append(
            Event(
                event_id=f"1-{seq}",
                event_type=etype,
                timestamp_ns=seq * 1000,
                sequence=seq,
                process_id=1,
                thread_id=thread,
                metadata=meta,
                **kw,
            )
        )
        return f"1-{seq}"

    def replay(self, meta=None):
        return build_replay(Trace(meta or {}, self.events))


def base(maxsize=2):
    s = Script()
    s.add(E.THREAD_REGISTERED, "thread-1", metadata={"name": "P"})
    s.add(E.THREAD_REGISTERED, "thread-2", metadata={"name": "C"})
    s.add(
        E.QUEUE_CREATED,
        resource_id="queue-1",
        metadata={"name": "Q", "maxsize": maxsize},
    )
    return s


def put(s, oid, op, size):
    s.add(
        E.QUEUE_PUT_STARTED,
        resource_id="queue-1",
        object_id=oid,
        operation_id=op,
        metadata={"type": "str"},
    )
    return s.add(
        E.QUEUE_PUT_COMPLETED,
        resource_id="queue-1",
        object_id=oid,
        operation_id=op,
        metadata={"size_after": size},
    )


def test_occupancy_and_unfinished_are_distinct():
    s = base()
    put(s, "object-1", "op-1", 1)
    s.add(
        E.QUEUE_GET_STARTED,
        "thread-2",
        resource_id="queue-1",
        operation_id="op-2",
    )
    s.add(
        E.QUEUE_GET_COMPLETED,
        "thread-2",
        resource_id="queue-1",
        object_id="object-1",
        operation_id="op-2",
        metadata={"size_after": 0},
    )
    r = s.replay()
    q = state_after(r, len(s.events) - 1)["queues"]["queue-1"]
    assert q["items"] == [] and q["unfinished"] == 1
    last = r["frames"][-1]["explanation"]["text"]
    assert "no longer occupies the queue" in last and "unfinished" in last
    assert r["warnings"] == []


def test_task_done_without_object_is_inferred_not_asserted():
    s = base()
    put(s, "object-1", "op-1", 1)
    s.add(
        E.QUEUE_GET_COMPLETED,
        "thread-2",
        resource_id="queue-1",
        object_id="object-1",
        operation_id="op-2",
        metadata={"size_after": 0},
    )
    s.add(
        E.QUEUE_TASK_DONE,
        "thread-2",
        resource_id="queue-1",
        operation_id="op-3",
    )
    r = s.replay()
    ex = r["frames"][-1]["explanation"]
    assert "does not say which item finished" in ex["text"]
    assert ex["inferred"], "release of the held item must be labelled inferred"
    w = state_after(r, len(s.events) - 1)
    assert w["queues"]["queue-1"]["unfinished"] == 0
    assert w["objects"]["object-1"]["phase"] == "released"


def test_explicit_task_done_is_not_inferred():
    s = base()
    put(s, "object-1", "op-1", 1)
    s.add(
        E.QUEUE_GET_COMPLETED,
        "thread-2",
        resource_id="queue-1",
        object_id="object-1",
        operation_id="op-2",
        metadata={"size_after": 0},
    )
    s.add(
        E.QUEUE_TASK_DONE,
        "thread-2",
        resource_id="queue-1",
        object_id="object-1",
        operation_id="op-3",
    )
    assert s.replay()["frames"][-1]["explanation"]["inferred"] == []


def test_blocked_put_state_and_explanation():
    s = base(maxsize=1)
    put(s, "object-1", "op-1", 1)
    s.add(
        E.QUEUE_PUT_STARTED,
        "thread-1",
        resource_id="queue-1",
        object_id="object-2",
        operation_id="op-2",
    )
    s.add(
        E.QUEUE_PUT_BLOCKED,
        "thread-1",
        resource_id="queue-1",
        object_id="object-2",
        operation_id="op-2",
        metadata={"reason": "full"},
    )
    r = s.replay()
    i = len(s.events) - 1
    w = state_after(r, i)
    assert w["threads"]["thread-1"]["status"] == "waiting"
    assert w["queues"]["queue-1"]["blocked_puts"][0]["object"] == "object-2"
    assert "was full (1/1)" in r["frames"][i]["explanation"]["text"]
    # ...and it resumes once a consumer makes room.
    s.add(
        E.QUEUE_GET_COMPLETED,
        "thread-2",
        resource_id="queue-1",
        object_id="object-1",
        operation_id="op-3",
        metadata={"size_after": 0},
    )
    s.add(
        E.QUEUE_PUT_COMPLETED,
        "thread-1",
        resource_id="queue-1",
        object_id="object-2",
        operation_id="op-2",
        metadata={"size_after": 1},
    )
    r = s.replay()
    w = state_after(r, len(s.events) - 1)
    assert w["threads"]["thread-1"]["status"] == "running"
    assert w["queues"]["queue-1"]["blocked_puts"] == []
    assert w["queues"]["queue-1"]["items"] == ["object-2"]
    spans = [x for x in r["spans"] if x["kind"] == "wait_put"]
    assert len(spans) == 1 and spans[0]["outcome"] == "completed"


def test_immediate_shutdown_discards_and_reduces_unfinished():
    s = base()
    put(s, "object-1", "op-1", 1)
    put(s, "object-2", "op-2", 2)
    s.add(
        E.QUEUE_SHUTDOWN_REQUESTED,
        resource_id="queue-1",
        operation_id="op-3",
        metadata={"immediate": True},
    )
    for oid in ("object-1", "object-2"):
        s.add(
            E.QUEUE_ITEM_DISCARDED,
            resource_id="queue-1",
            object_id=oid,
            metadata={"size_after": 0},
        )
    r = s.replay()
    q = state_after(r, len(s.events) - 1)["queues"]["queue-1"]
    assert q["shutdown"] == "immediate"
    assert q["items"] == [] and q["unfinished"] == 0


def test_size_mismatch_is_reported_not_hidden():
    s = base()
    put(s, "object-1", "op-1", 5)  # recorded size disagrees with replay
    assert any("disagrees" in w for w in s.replay()["warnings"])


def test_truncated_trace_warns():
    s = base()
    r = s.replay({"truncated": True, "dropped_events": 7})
    assert "truncated" in r["warnings"][0] and "7" in r["warnings"][0]


def test_replay_is_deterministic():
    s = base()
    put(s, "object-1", "op-1", 1)
    assert s.replay() == s.replay()


def test_unknown_event_type_is_tolerated():
    s = base()
    s.add("future.event")
    r = s.replay()
    assert any("unknown event type" in w for w in r["warnings"])
