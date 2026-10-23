"""Real threads and real queue operations, verified against what the
program itself observed (not against fixed schedules)."""

import queue
import threading

import pytest

import concurim
from concurim.recorder.events import EventType as E
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import TIMEOUT, types, wait_for, world_after


def replay_of(rec):
    return build_replay(Trace({}, rec.events()))


def seq_of(events, etype, **match):
    for e in events:
        if e.event_type == etype and all(
            e.metadata.get(k) == v for k, v in match.items()
        ):
            return e.sequence
    raise AssertionError(f"no {etype} {match}")


def test_behaves_like_queue_without_recording():
    q = concurim.TracedQueue(maxsize=2, name="plain")
    payload = object()
    q.put(payload)
    q.put_nowait(1)
    with pytest.raises(queue.Full):
        q.put_nowait(2)
    assert q.get() is payload
    assert q.get_nowait() == 1
    with pytest.raises(queue.Empty):
        q.get_nowait()
    assert concurim.active_recorder() is None
    assert isinstance(q, queue.Queue)


def test_blocked_put_resumes_after_get(rec):
    q = concurim.TracedQueue(maxsize=1, name="Q")
    q.put("a")
    t = threading.Thread(target=lambda: q.put("b"))
    t.start()
    wait_for(lambda: E.QUEUE_PUT_BLOCKED in types(rec.events()))
    assert q.get() == "a"
    t.join(TIMEOUT)
    ev = rec.events()
    second_put = [
        e.sequence for e in ev if e.event_type == E.QUEUE_PUT_COMPLETED
    ][-1]
    assert (
        seq_of(ev, E.QUEUE_PUT_BLOCKED)
        < seq_of(ev, E.QUEUE_GET_COMPLETED)
        < second_put
    )
    r = replay_of(rec)
    assert r["warnings"] == []
    assert [s["outcome"] for s in r["spans"] if s["kind"] == "wait_put"] == [
        "completed"
    ]


def test_blocked_get_receives_the_exact_object_with_causal_edge(rec):
    q = concurim.TracedQueue(name="Q")
    got = []
    t = threading.Thread(target=lambda: got.append(q.get_with_id()))
    t.start()
    wait_for(lambda: E.QUEUE_GET_BLOCKED in types(rec.events()))
    payload = {"unhashable": [1]}
    q.put(payload)
    t.join(TIMEOUT)
    assert got[0].value is payload
    ev = {e.event_id: e for e in rec.events()}
    done = next(e for e in ev.values() if e.event_type == E.QUEUE_GET_COMPLETED)
    assert done.object_id == got[0].object_id
    assert ev[done.caused_by].event_type == E.QUEUE_PUT_COMPLETED
    assert ev[done.caused_by].object_id == done.object_id


def test_nowait_calls_record_exactly_one_operation(rec):
    q = concurim.TracedQueue(maxsize=1, name="Q")
    q.put_nowait("a")
    with pytest.raises(queue.Full):
        q.put_nowait("b")
    q.get_nowait()
    with pytest.raises(queue.Empty):
        q.get_nowait()
    ev = rec.events()
    assert types(ev, "queue.put").count(E.QUEUE_PUT_STARTED) == 2
    assert types(ev, "queue.get").count(E.QUEUE_GET_STARTED) == 2
    assert E.QUEUE_PUT_BLOCKED not in types(ev)
    failed = [e for e in ev if e.event_type == E.QUEUE_PUT_FAILED]
    assert [e.metadata["reason"] for e in failed] == ["full"]
    assert [
        e.metadata["reason"] for e in ev if e.event_type == E.QUEUE_GET_FAILED
    ] == ["empty"]


def test_timeouts_are_recorded_and_raise_stdlib_exceptions(rec):
    q = concurim.TracedQueue(maxsize=1, name="Q")
    with pytest.raises(queue.Empty):
        q.get(timeout=0.02)
    q.put("a")
    with pytest.raises(queue.Full):
        q.put("b", timeout=0.02)
    t = types(rec.events())
    assert E.QUEUE_GET_BLOCKED in t and E.QUEUE_GET_TIMEOUT in t
    assert E.QUEUE_PUT_BLOCKED in t and E.QUEUE_PUT_TIMEOUT in t
    assert replay_of(rec)["warnings"] == []


def test_negative_timeout_matches_stdlib(rec):
    q = concurim.TracedQueue(maxsize=1)
    with pytest.raises(ValueError, match="non-negative"):
        q.get(timeout=-1)
    with pytest.raises(ValueError, match="non-negative"):
        q.put(1, timeout=-1)


def test_join_waits_for_last_task_done(rec):
    q = concurim.TracedQueue(name="Q")
    q.put(1)
    q.put(2)
    joined = threading.Event()

    def joiner():
        q.join()
        joined.set()

    t = threading.Thread(target=joiner)
    t.start()
    wait_for(lambda: E.QUEUE_JOIN_STARTED in types(rec.events()))
    q.get(), q.task_done()
    assert not joined.wait(0.05)
    q.get(), q.task_done()
    t.join(TIMEOUT)
    assert joined.is_set()
    ev = rec.events()
    last_done = [e.sequence for e in ev if e.event_type == E.QUEUE_TASK_DONE]
    assert last_done[-1] < seq_of(ev, E.QUEUE_JOIN_COMPLETED)
    r = replay_of(rec)
    assert [s["outcome"] for s in r["spans"] if s["kind"] == "wait_join"] == [
        "completed"
    ]


def test_task_done_too_many_times(rec):
    q = concurim.TracedQueue()
    with pytest.raises(ValueError):
        q.task_done()
    assert E.QUEUE_TASK_DONE_FAILED in types(rec.events())


def test_occupancy_differs_from_unfinished_in_replay(rec):
    q = concurim.TracedQueue(name="Q")
    q.put("x")
    q.get()
    r = replay_of(rec)
    assert r["occupancy"]["queue-1"][-1][1:] == [0, 1]  # size 0, unfinished 1


def test_graceful_shutdown_drains_then_raises(rec):
    q = concurim.TracedQueue(name="Q")
    q.put(1)
    q.put(2)
    q.shutdown()
    with pytest.raises(queue.ShutDown):
        q.put(3)
    assert (q.get(), q.get()) == (1, 2)
    with pytest.raises(queue.ShutDown):
        q.get()
    ev = rec.events()
    assert E.QUEUE_ITEM_DISCARDED not in types(ev)
    reasons = [
        e.metadata.get("reason")
        for e in ev
        if e.event_type in (E.QUEUE_PUT_FAILED, E.QUEUE_GET_FAILED)
    ]
    assert reasons == ["shutdown", "shutdown"]
    assert replay_of(rec)["warnings"] == []


def test_immediate_shutdown_discards_and_wakes_waiters(rec):
    q = concurim.TracedQueue(maxsize=1, name="Q")
    q.put("kept-out")
    errors = []

    def blocked_put():
        try:
            q.put("never")
        except queue.ShutDown as exc:
            errors.append(exc)

    t = threading.Thread(target=blocked_put)
    t.start()
    wait_for(lambda: E.QUEUE_PUT_BLOCKED in types(rec.events()))
    q.shutdown(immediate=True)
    t.join(TIMEOUT)
    assert len(errors) == 1
    ev = rec.events()
    assert seq_of(ev, E.QUEUE_SHUTDOWN_REQUESTED) < seq_of(
        ev, E.QUEUE_ITEM_DISCARDED
    )
    assert seq_of(ev, E.QUEUE_SHUTDOWN_REQUESTED) < seq_of(
        ev, E.QUEUE_PUT_FAILED
    )
    r = replay_of(rec)
    assert r["warnings"] == []
    state = world_after(r)["queues"]["queue-1"]
    assert state["items"] == [] and state["unfinished"] == 0
