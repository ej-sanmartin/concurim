"""Locks, semaphores and executors: recorded accurately, and honestly."""

import concurrent.futures
import threading
import time

import pytest

import concurim
from concurim.instrumentation.auto import auto_instrument
from concurim.recorder.environment import coverage_for
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import TIMEOUT, types, wait_for, world_after


def replay_of(rec):
    return build_replay(Trace({"program": {}}, rec.events(), {}))


def test_contended_lock_shows_a_waiter_and_a_hold(rec):
    lock = concurim.TracedLock(name="L")
    gate = threading.Event()

    def holder():
        with lock:
            gate.set()
            wait_for(lambda: "lock.acquire.blocked" in types(rec.events()))

    def waiter():
        gate.wait(TIMEOUT)
        with lock:
            pass

    for t in (holder, waiter):
        concurim.TracedThread(target=t).start()
    wait_for(lambda: types(rec.events()).count(E.LOCK_RELEASED) == 2)
    ev = types(rec.events(), "lock.")
    assert ev.count(E.LOCK_ACQUIRE_BLOCKED) == 1
    # The waiter acquires only after the holder released.
    assert ev.index(E.LOCK_RELEASED) < max(
        i for i, t in enumerate(ev) if t == E.LOCK_ACQUIRE_COMPLETED
    )
    r = replay_of(rec)
    kinds = [s["kind"] for s in r["spans"]]
    assert kinds.count("wait_lock") == 1 and kinds.count("hold") == 2
    lock_state = world_after(r)["syncs"]["lock-1"]
    assert lock_state["holders"] == [] and lock_state["waiters"] == []
    assert r["warnings"] == []


def test_lock_midway_shows_who_holds_and_who_waits(rec):
    lock = concurim.TracedLock()
    release = threading.Event()
    lock.acquire()

    def waiter():
        lock.acquire()
        lock.release()

    t = concurim.TracedThread(target=waiter, name="waiter")
    t.start()
    wait_for(lambda: E.LOCK_ACQUIRE_BLOCKED in types(rec.events()))
    r = replay_of(rec)
    state = world_after(r)["syncs"]["lock-1"]
    assert len(state["holders"]) == 1 and len(state["waiters"]) == 1
    waiting = [
        th
        for th in world_after(r)["threads"].values()
        if th["status"] == "waiting"
    ]
    assert waiting[0]["name"] == "waiter"
    assert waiting[0]["waiting_on"]["resource"] == "lock-1"
    lock.release()
    t.join(TIMEOUT)
    release.set()


def test_nonblocking_and_timeout_failures_are_recorded(rec):
    lock = concurim.TracedLock()
    lock.acquire()
    assert lock.acquire(False) is False
    assert lock.acquire(True, 0.01) is False
    lock.release()
    failed = [e for e in rec.events() if e.event_type == E.LOCK_ACQUIRE_FAILED]
    assert [e.metadata["reason"] for e in failed] == [
        "nonblocking",
        "timeout",
    ]


def test_invalid_arguments_still_raise_as_before(rec):
    lock = concurim.TracedLock()
    with pytest.raises(ValueError):
        lock.acquire(False, 1)
    with pytest.raises(RuntimeError):
        lock.release()


def test_rlock_records_each_level_and_supports_conditions(rec):
    rlock = concurim.TracedRLock(name="R")
    with rlock, rlock:
        cond = threading.Condition(rlock)
        with cond:
            cond.notify_all()
    ev = types(rec.events(), "lock.")
    assert ev.count(E.LOCK_ACQUIRE_COMPLETED) == 3
    assert ev.count(E.LOCK_RELEASED) == 3
    r = replay_of(rec)
    assert world_after(r)["syncs"]["lock-1"]["holders"] == []
    assert next(iter(r["entities"]["syncs"].values()))["kind"] == "rlock"


def test_semaphore_tracks_permits_and_blocking(rec):
    sem = concurim.TracedSemaphore(2, name="S")
    sem.acquire()
    sem.acquire()
    done = threading.Event()

    def third():
        with sem:
            done.set()

    concurim.TracedThread(target=third).start()
    wait_for(lambda: E.SEMAPHORE_ACQUIRE_BLOCKED in types(rec.events()))
    mid = world_after(replay_of(rec))["syncs"]["semaphore-1"]
    assert mid["value"] == 0 and len(mid["waiters"]) == 1
    sem.release()
    assert done.wait(TIMEOUT)
    sem.release()
    wait_for(lambda: types(rec.events()).count(E.SEMAPHORE_RELEASED) == 3)
    end = world_after(replay_of(rec))["syncs"]["semaphore-1"]
    assert end["value"] == 2 and end["capacity"] == 2


def test_bounded_semaphore_over_release_still_raises(rec):
    sem = concurim.TracedBoundedSemaphore(1)
    with pytest.raises(ValueError):
        sem.release()
    assert E.SEMAPHORE_RELEASED not in types(rec.events())


def test_traced_primitives_are_plain_outside_a_recording():
    lock, sem = concurim.TracedLock(), concurim.TracedSemaphore(1)
    with lock, sem:
        assert lock.locked()
    assert not lock.locked()


def test_executor_records_the_journey_of_each_task(rec):
    def job(n):
        if n == 2:
            raise ValueError("expected")
        return n

    with concurim.TracedThreadPoolExecutor(max_workers=1, name="Pool") as pool:
        futures = [pool.submit(job, i) for i in range(3)]
    assert [f.exception() is None for f in futures] == [True, True, False]
    ev = types(rec.events(), "executor.")
    assert ev.count(E.EXECUTOR_SUBMIT) == 3
    assert ev.count(E.EXECUTOR_TASK_STARTED) == 3
    assert ev.count(E.EXECUTOR_TASK_FAILED) == 1
    assert E.EXECUTOR_SHUTDOWN in ev
    r = replay_of(rec)
    pool = r["entities"]["queues"]["executor-1"]
    assert pool["kind"] == "executor" and pool["workers"] == 1
    end = world_after(r)["queues"]["executor-1"]
    assert end["items"] == [] and end["unfinished"] == 0
    assert end["running"] == 0 and end["shutdown"] == "graceful"
    assert {o["phase"] for o in world_after(r)["objects"].values()} == {
        "released"
    }
    assert r["warnings"] == []


def test_executor_cancel_futures_discards_pending_tasks(rec):
    gate = threading.Event()
    pool = concurim.TracedThreadPoolExecutor(max_workers=1)
    pool.submit(gate.wait, TIMEOUT)
    wait_for(lambda: E.EXECUTOR_TASK_STARTED in types(rec.events()))
    pool.submit(time.sleep, 0)
    pool.submit(time.sleep, 0)
    pool.shutdown(wait=False, cancel_futures=True)
    gate.set()
    pool.shutdown(wait=True)
    q = world_after(replay_of(rec))["queues"]["executor-1"]
    assert q["items"] == [] and q["shutdown"] == "immediate"


def test_auto_sync_traces_only_user_created_primitives():
    with record(auto="sync") as rec:
        lock = threading.Lock()
        event = threading.Event()  # its internal lock is not user code
        sem = threading.Semaphore(1)
        with lock, sem:
            event.set()
        pool_class = concurrent.futures.ThreadPoolExecutor  # patched now
        with pool_class(max_workers=1) as pool:
            pool.submit(lambda: None).result(TIMEOUT)
    ev = types(rec.events())
    assert ev.count(E.LOCK_CREATED) == 1  # not the Event's
    assert ev.count(E.SEMAPHORE_CREATED) == 1
    assert ev.count(E.EXECUTOR_CREATED) == 1
    names = [
        e.metadata["name"]
        for e in rec.events()
        if e.event_type.endswith(".created")
    ]
    assert all("(line " in n for n in names)


def test_auto_sync_restores_everything_and_is_reversible():
    before = (
        threading.Lock,
        threading.RLock,
        threading.Semaphore,
        threading.BoundedSemaphore,
        concurrent.futures.ThreadPoolExecutor,
    )
    with pytest.raises(RuntimeError), auto_instrument("sync"):
        assert threading.Lock is not before[0]
        raise RuntimeError
    assert (
        threading.Lock,
        threading.RLock,
        threading.Semaphore,
        threading.BoundedSemaphore,
        concurrent.futures.ThreadPoolExecutor,
    ) == before


def test_lower_levels_do_not_see_locks_and_say_so():
    with record(auto="queues") as rec:
        lock = threading.Lock()
        with lock:
            pass
    assert types(rec.events(), "lock.") == []
    text = " ".join(coverage_for("queues")["not_observed"])
    assert "locks" in text
    assert "locks" not in " ".join(
        x for x in coverage_for("sync")["not_observed"] if "Plain" in x
    )


def test_queue_contents_hide_internal_envelopes():
    with record(auto="queues"):
        import queue

        q = queue.Queue()
        q.put("a")
        q.put(2)
        assert list(q.queue) == ["a", 2]
        assert q.queue[0] == "a" and 2 in q.queue
        assert q.get() == "a"
