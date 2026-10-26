"""Futures after submit: cancellation, done-callbacks and as_completed."""

import concurrent.futures
import threading
import time

from concurim.instrumentation.auto import auto_instrument
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import TIMEOUT, types, world_after


def replay_of(rec):
    return build_replay(Trace({"program": {}}, rec.events(), {}))


def blocked_pool(rec_events=None):
    """A one-worker pool whose only worker is busy until ``gate`` is set."""
    gate = threading.Event()
    started = threading.Event()

    def hold():
        started.set()
        gate.wait(TIMEOUT)

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    first = pool.submit(hold)
    assert started.wait(TIMEOUT)
    return pool, first, gate


def test_cancelling_a_pending_task_is_recorded_and_it_never_runs():
    ran = []
    with record(auto="sync") as rec:
        pool, first, gate = blocked_pool()
        second = pool.submit(lambda: ran.append("second"))
        assert second.cancel() is True
        gate.set()
        pool.shutdown()
    assert first.result() is None and ran == []
    cancelled = [
        e for e in rec.events() if e.event_type == E.EXECUTOR_TASK_CANCELLED
    ]
    assert len(cancelled) == 1
    assert types(rec.events()).count(E.EXECUTOR_TASK_STARTED) == 1
    r = replay_of(rec)
    assert r["warnings"] == []
    final = world_after(r)
    pool_state = next(iter(final["queues"].values()))
    assert pool_state["size"] == 0 and pool_state["unfinished"] == 0
    assert final["objects"][cancelled[0].object_id]["phase"] == "discarded"
    titles = [f["explanation"]["title"] for f in r["frames"]]
    assert "Task cancelled" in titles


def test_cancelling_a_running_task_fails_and_records_nothing():
    with record(auto="sync") as rec:
        pool, first, gate = blocked_pool()
        assert first.cancel() is False
        gate.set()
        pool.shutdown()
    assert E.EXECUTOR_TASK_CANCELLED not in types(rec.events())


def test_shutdown_cancel_futures_is_one_event_not_one_per_task():
    with record(auto="sync") as rec:
        pool, _, gate = blocked_pool()
        for _ in range(3):
            pool.submit(lambda: None)
        pool.shutdown(wait=False, cancel_futures=True)
        gate.set()
        pool.shutdown()
    ev = types(rec.events())
    assert ev.count(E.EXECUTOR_SHUTDOWN) == 1
    assert E.EXECUTOR_TASK_CANCELLED not in ev
    assert replay_of(rec)["warnings"] == []


def test_callback_runs_on_the_completing_worker_not_the_caller():
    seen = []
    with record(auto="sync") as rec:
        pool, first, gate = blocked_pool()
        first.add_done_callback(
            lambda f: seen.append(threading.current_thread().name)
        )
        gate.set()
        first.result(TIMEOUT)
        pool.shutdown()
    assert seen and seen[0] != threading.current_thread().name
    callbacks = [e for e in rec.events() if e.event_type == E.EXECUTOR_CALLBACK]
    assert len(callbacks) == 1
    assert callbacks[0].metadata["outcome"] == "finished"
    main_actor = rec.events()[0].thread_id
    assert callbacks[0].thread_id != main_actor


def test_callback_added_after_completion_runs_on_the_caller():
    with record(auto="sync") as rec:
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(lambda: 1)
        future.result(TIMEOUT)
        future.add_done_callback(lambda f: None)
        pool.shutdown()
    callbacks = [e for e in rec.events() if e.event_type == E.EXECUTOR_CALLBACK]
    assert len(callbacks) == 1
    assert callbacks[0].thread_id == rec.events()[0].thread_id


def test_as_completed_records_the_order_tasks_come_back():
    with record(auto="sync") as rec:
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        slow = pool.submit(time.sleep, 0.15)
        fast = pool.submit(lambda: "fast")
        order = list(concurrent.futures.as_completed([slow, fast]))
        pool.shutdown()
    assert order == [fast, slow]
    collected = [
        e for e in rec.events() if e.event_type == E.EXECUTOR_COLLECTED
    ]
    assert [e.metadata["order"] for e in collected] == [1, 2]
    submits = [
        e.object_id for e in rec.events() if e.event_type == E.EXECUTOR_SUBMIT
    ]
    # Collected in completion order: fast (submitted second) came first.
    assert [e.object_id for e in collected] == [submits[1], submits[0]]
    assert replay_of(rec)["warnings"] == []


def test_as_completed_is_untouched_outside_a_recording():
    original = concurrent.futures.as_completed
    with auto_instrument("sync"):
        assert concurrent.futures.as_completed is not original
    assert concurrent.futures.as_completed is original
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        futures = [pool.submit(pow, 2, n) for n in range(3)]
        done = sorted(
            f.result() for f in concurrent.futures.as_completed(futures)
        )
    assert done == [1, 2, 4]
