"""Fail states read off a run: stranded locks, lock order, lost signals."""

import asyncio
import queue
import threading
from types import SimpleNamespace

import pytest

import concurim
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import TIMEOUT, run_threads, types, wait_for


def replay_of(rec):
    return build_replay(Trace({"program": {}}, rec.events(), {}))


def kinds(replay):
    return [h["kind"] for h in replay["hazards"]]


def hazard(replay, kind):
    return next(h for h in replay["hazards"] if h["kind"] == kind)


def test_a_clean_run_has_no_hazards(rec):
    lock = concurim.TracedLock(name="L")

    def work():
        with lock:
            pass

    run_threads(work, work)
    r = replay_of(rec)
    assert r["hazards"] == [] and r["warnings"] == []


def test_opposite_lock_order_is_flagged_as_a_pattern(rec):
    a, b = concurim.TracedLock(name="A"), concurim.TracedLock(name="B")
    ready = threading.Barrier(2)

    def take(first, second):
        with first:
            ready.wait(TIMEOUT)
            if second.acquire(timeout=0.2):
                second.release()

    run_threads(lambda: take(a, b), lambda: take(b, a))
    r = replay_of(rec)
    found = hazard(r, "lock_order")
    assert found["inferred"] is True
    assert "opposite order" in found["text"]
    assert "A" in found["text"] and "B" in found["text"]
    assert kinds(r).count("lock_order") == 1  # one pair, said once


def test_one_consistent_lock_order_is_not_flagged(rec):
    a, b = concurim.TracedLock(name="A"), concurim.TracedLock(name="B")

    def both():
        with a, b:
            pass

    run_threads(both, both)
    assert "lock_order" not in kinds(replay_of(rec))


def test_non_blocking_nested_acquires_are_not_an_ordering(rec):
    a, b = concurim.TracedLock(name="A"), concurim.TracedLock(name="B")
    gate = threading.Barrier(2)

    def take(first, second):
        with first:
            gate.wait(TIMEOUT)
            if second.acquire(False):
                second.release()

    run_threads(lambda: take(a, b), lambda: take(b, a))
    assert "lock_order" not in kinds(replay_of(rec))


def test_a_lock_whose_holder_ended_strands_its_waiter(rec):
    lock = concurim.TracedLock(name="Door")
    run_threads(lock.acquire)  # takes it and ends without releasing
    waiter = concurim.TracedThread(
        target=lambda: (lock.acquire(), lock.release()), name="late"
    )
    waiter.start()
    wait_for(lambda: E.LOCK_ACQUIRE_BLOCKED in types(rec.events()))
    r = replay_of(rec)
    found = hazard(r, "holder_gone")
    assert found["inferred"] is False
    assert "late waits for Door" in found["text"]
    assert "ended while holding it" in found["text"]
    lock.release()  # another thread may release a plain Lock
    waiter.join(TIMEOUT)


def test_a_waiter_with_a_timeout_is_not_called_stranded(rec):
    lock = concurim.TracedLock(name="Door")
    run_threads(lock.acquire)
    run_threads(lambda: lock.acquire(timeout=0.05))
    assert "holder_gone" not in kinds(replay_of(rec))


def test_a_wait_after_every_putter_ended_is_flagged_inferred(rec):
    q = concurim.TracedQueue(name="Jobs")
    run_threads(lambda: q.put(1))
    got = []

    def consume():
        got.append(q.get())
        q.get()  # nothing will ever arrive

    consumer = concurim.TracedThread(target=consume, name="eater")
    consumer.start()
    wait_for(lambda: E.QUEUE_GET_BLOCKED in types(rec.events()))
    found = hazard(replay_of(rec), "lost_signal")
    assert found["inferred"] is True
    assert "every thread that ever put to it" in found["text"]
    q.put(2)  # let the consumer go
    consumer.join(TIMEOUT)


def test_a_get_with_a_timeout_is_not_called_lost(rec):
    q = concurim.TracedQueue(name="Jobs")
    run_threads(lambda: q.put(1))

    def consume():
        q.get()
        with pytest.raises(queue.Empty):
            q.get(timeout=0.05)

    run_threads(consume)
    assert "lost_signal" not in kinds(replay_of(rec))


def test_an_event_nobody_can_set_any_more_is_flagged(rec):
    ready = concurim.TracedEvent(name="Ready")
    run_threads(lambda: (ready.set(), ready.clear()))
    waiter = concurim.TracedThread(target=ready.wait, name="sleeper")
    waiter.start()
    wait_for(lambda: E.EVENT_WAIT_BLOCKED in types(rec.events()))
    found = hazard(replay_of(rec), "lost_signal")
    assert "calls set()" in found["text"]
    ready.set()
    waiter.join(TIMEOUT)


def test_join_that_can_never_return_is_flagged_not_inferred(rec):
    q = concurim.TracedQueue(name="Jobs")
    q.put("a")
    run_threads(q.get)  # takes the item, never calls task_done()
    joiner = concurim.TracedThread(target=q.join, name="waiter")
    joiner.start()
    wait_for(lambda: E.QUEUE_JOIN_STARTED in types(rec.events()))
    found = hazard(replay_of(rec), "join_stuck")
    assert found["inferred"] is False
    assert "ended without calling task_done()" in found["text"]
    q.task_done()
    joiner.join(TIMEOUT)


def test_join_waiting_on_a_running_worker_is_fine(rec):
    q = concurim.TracedQueue(name="Jobs")
    q.put("a")
    got = threading.Event()
    done = threading.Event()

    def worker():
        q.get()
        got.set()
        done.wait(TIMEOUT)
        q.task_done()

    t = concurim.TracedThread(target=worker)
    t.start()
    got.wait(TIMEOUT)
    joiner = concurim.TracedThread(target=q.join)
    joiner.start()
    wait_for(lambda: E.QUEUE_JOIN_STARTED in types(rec.events()))
    assert "join_stuck" not in kinds(replay_of(rec))
    done.set()
    t.join(TIMEOUT)
    joiner.join(TIMEOUT)


def test_a_task_blocked_on_a_thread_lock_stops_the_loop():
    with record(auto="asyncio") as rec:
        lock = concurim.TracedLock(name="Gate")
        lock.acquire()

        async def main():
            threading.Timer(0.1, lock.release).start()
            lock.acquire()  # blocks the whole loop for a moment
            lock.release()

        asyncio.run(main())
    found = hazard(replay_of(rec), "loop_blocked")
    assert found["inferred"] is False
    assert "stops its whole event loop thread" in found["text"]


def test_a_task_waiting_on_an_asyncio_lock_is_normal():
    async def main():
        lock = concurim.TracedAsyncLock(name="Gate")
        await lock.acquire()

        async def waiter():
            async with lock:
                pass

        task = asyncio.create_task(waiter())
        await asyncio.sleep(0.01)
        lock.release()
        await task

    with record(auto="asyncio") as rec:
        asyncio.run(main())
    assert "loop_blocked" not in kinds(replay_of(rec))


def test_fork_while_another_thread_holds_a_lock_is_flagged(rec):
    lock = concurim.TracedLock(name="Db")
    held, leave = threading.Event(), threading.Event()

    def holder():
        with lock:
            held.set()
            leave.wait(TIMEOUT)

    t = concurim.TracedThread(target=holder, name="keeper")
    t.start()
    held.wait(TIMEOUT)
    for method in ("fork", "spawn"):
        rec.emit(
            E.THREAD_START_REQUESTED,
            metadata={
                "child_name": f"child-{method}",
                "process": True,
                "start_method": method,
            },
        )
    r = replay_of(rec)
    found = [h for h in r["hazards"] if h["kind"] == "fork_lock"]
    assert len(found) == 1 and "child-fork" in found[0]["text"]
    assert "keeper" in found[0]["text"]
    leave.set()
    t.join(TIMEOUT)


def test_fork_pool_while_another_thread_holds_a_lock_is_flagged(rec):
    lock = concurim.TracedLock(name="Db")
    held, leave = threading.Event(), threading.Event()

    def holder():
        with lock:
            held.set()
            leave.wait(TIMEOUT)

    t = concurim.TracedThread(target=holder, name="keeper")
    t.start()
    held.wait(TIMEOUT)
    for method in ("fork", "spawn"):
        rec.resource_id(  # emits executor.created
            SimpleNamespace(),
            "executor",
            f"Pool-{method}",
            {"pool": "process", "start_method": method},
        )
    found = [h for h in replay_of(rec)["hazards"] if h["kind"] == "fork_lock"]
    assert len(found) == 1
    assert "workers of Pool-fork are started by fork" in found[0]["text"]
    leave.set()
    t.join(TIMEOUT)


def test_hazards_appear_in_the_event_explanation_and_the_warnings(rec):
    lock = concurim.TracedLock(name="Door")
    run_threads(lock.acquire)
    waiter = concurim.TracedThread(target=lock.acquire, name="late")
    waiter.start()
    wait_for(lambda: E.LOCK_ACQUIRE_BLOCKED in types(rec.events()))
    r = replay_of(rec)
    at = hazard(r, "holder_gone")["at"]
    assert "ended while holding it" in r["frames"][at]["explanation"]["text"]
    assert any("ended while holding it" in w for w in r["warnings"])
    lock.release()
    waiter.join(TIMEOUT)
