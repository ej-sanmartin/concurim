"""multiprocessing locks and values: every process shows up on one lock."""

import multiprocessing
import multiprocessing.synchronize

import pool_tasks
import pytest

import concurim
from concurim.config import RecorderConfig
from concurim.instrumentation.auto import auto_instrument
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import types, world_after


def replay_of(rec):
    return build_replay(Trace({"program": {}}, rec.events(), {}))


def run_children(*targets):
    procs = [
        concurim.TracedProcess(target=fn, args=args, name=f"child-{i}")
        for i, (fn, args) in enumerate(targets, 1)
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join()
        assert proc.exitcode == 0
    return procs


def kinds(replay):
    return [h["kind"] for h in replay["hazards"]]


def test_one_lock_shows_every_process_that_takes_it(rec):
    lock = concurim.TracedMPLock(name="Door")
    counter = concurim.traced_value("i", 0, lock=False, name="count")
    run_children(*[(pool_tasks.locked_bump, (lock, counter))] * 3)
    assert counter.value == 3
    r = replay_of(rec)
    taking = {
        e.thread_id
        for e in rec.events()
        if e.event_type == E.LOCK_ACQUIRE_COMPLETED
    }
    assert len(taking) == 3 and all(t.startswith("process") for t in taking)
    end = world_after(r)
    assert end["syncs"]["lock-1"]["holders"] == []
    assert end["syncs"]["lock-1"]["kind"] == "lock"
    assert r["warnings"] == [] and r["hazards"] == []


def test_a_lock_held_by_one_process_does_not_poison_the_next_fork(rec):
    concurim.TracedMPLock(name="Door")
    created = next(
        e for e in rec.events() if e.event_type == E.LOCK_CREATED
    )
    child = rec.remote_actor("child", "child-1", 1)
    rec.emit_as(
        child,
        E.LOCK_ACQUIRE_COMPLETED,
        resource_id=created.resource_id,
    )
    rec.emit(
        E.THREAD_START_REQUESTED,
        metadata={
            "child_name": "child-2",
            "process": True,
            "start_method": "fork",
        },
    )
    r = replay_of(rec)
    assert r["warnings"] == [] and r["hazards"] == []


def test_a_child_reports_the_line_that_took_the_lock(rec):
    lock = concurim.TracedMPLock(name="Door")
    run_children(
        (pool_tasks.locked_bump, (lock, concurim.traced_value("i", 0)))
    )
    taken = [
        e
        for e in rec.events()
        if e.event_type == E.LOCK_ACQUIRE_COMPLETED and e.source
    ]
    assert taken and taken[0].source.file.endswith("pool_tasks.py")


def test_values_are_shown_over_time_when_previews_are_on():
    with record(config=RecorderConfig(preview=True)) as rec:
        counter = concurim.traced_value("i", 0, name="count")
        run_children((pool_tasks.store, (counter, 5)))
        assert counter.value == 5
    r = replay_of(rec)
    texts = [f["explanation"]["text"] for f in r["frames"]]
    assert any("from 0 to 5" in t and "count lock" in t for t in texts)
    assert world_after(r)["syncs"]["cell-1"]["preview"] == "5"


def test_a_value_with_no_lock_is_flagged_across_processes(rec):
    counter = concurim.traced_value("i", 0, lock=False, name="count")
    barrier = multiprocessing.Barrier(2)  # keep both children alive
    run_children(*[(pool_tasks.bump_together, (counter, barrier))] * 2)
    # (the count may well be 1 here: that is the lost update itself)
    assert "unprotected_value" in kinds(replay_of(rec))


def test_a_values_own_lock_covers_each_access_but_not_the_increment(rec):
    counter = concurim.traced_value("i", 0, name="count")
    run_children(*[(pool_tasks.bump_value, (counter,))] * 2)
    r = replay_of(rec)
    # Each access is locked on its own, so the lockset sees protection...
    assert "unprotected_value" not in kinds(r)
    # ...but the read and the write were two separate holds.
    child = next(
        e.thread_id
        for e in rec.events()
        if e.event_type == E.LOCK_ACQUIRE_COMPLETED
    )
    holds = [
        e
        for e in rec.events()
        if e.event_type == E.LOCK_ACQUIRE_COMPLETED and e.thread_id == child
    ]
    assert len(holds) == 2


def test_a_reentrant_lock_in_a_child_shows_its_depth(rec):
    lock = concurim.TracedMPRLock(name="R")
    run_children((pool_tasks.reenter, (lock,)))
    r = replay_of(rec)
    titles = [f["explanation"]["title"] for f in r["frames"]]
    assert "Re-entered" in titles
    assert world_after(r)["syncs"]["lock-1"]["holders"] == []


def test_releases_the_locks_refuse_are_recorded_then_raised(rec):
    lock = concurim.TracedMPLock(name="L")
    with pytest.raises(ValueError):
        lock.release()
    rlock = concurim.TracedMPRLock(name="R")
    with pytest.raises(AssertionError):
        rlock.release()
    failed = [
        e.metadata["reason"]
        for e in rec.events()
        if e.event_type == E.LOCK_RELEASE_FAILED
    ]
    assert failed == ["not_locked", "not_acquired"]


def test_a_semaphore_counts_permits_across_the_replay(rec):
    sem = concurim.TracedMPSemaphore(2, name="Slots")
    sem.acquire()
    sem.acquire()
    assert sem.acquire(False) is False
    sem.release()
    sem.release()
    ev = types(rec.events(), "semaphore.")
    assert ev.count(E.SEMAPHORE_ACQUIRE_COMPLETED) == 2
    assert ev.count(E.SEMAPHORE_ACQUIRE_FAILED) == 1
    end = world_after(replay_of(rec))["syncs"]["semaphore-1"]
    assert end["value"] == 2 and end["capacity"] == 2


def test_the_traced_primitives_are_plain_outside_a_recording():
    lock = concurim.TracedMPLock()
    counter = concurim.traced_value("i", 1)
    with lock:
        counter.value += 1
    assert counter.value == 2 and not lock._semlock._is_zero()
    raw = concurim.traced_value("i", 3, lock=False)
    raw.value += 1
    assert raw.value == 4


def test_auto_sync_traces_only_what_user_code_creates():
    with record(auto="sync") as rec:
        lock = multiprocessing.Lock()
        rlock = multiprocessing.RLock()
        counter = multiprocessing.Value("i", 0)
        queue = multiprocessing.Queue()  # its internal locks are not ours
        with lock, rlock:
            counter.value += 1
        queue.close()
    names = [
        e.metadata["name"]
        for e in rec.events()
        if e.event_type == E.LOCK_CREATED
    ]
    assert len(names) == 3  # Lock, RLock, and the Value's own lock
    assert all("(line " in n for n in names), names
    cells = [
        e.metadata["name"]
        for e in rec.events()
        if e.event_type == "cell.created"
    ]
    assert "Value (line" in str(cells)


def _entry_points():
    ctx = multiprocessing.context.BaseContext
    return tuple(
        getattr(owner, name)
        for owner in (multiprocessing, ctx)
        for name in ("Lock", "RLock", "Semaphore", "BoundedSemaphore", "Value")
    )


def test_auto_sync_patches_are_reversible():
    before = _entry_points()
    with pytest.raises(RuntimeError), auto_instrument("sync"):
        assert _entry_points() != before
        raise RuntimeError
    assert _entry_points() == before


def test_auto_sync_also_traces_locks_from_a_named_context(rec):
    with auto_instrument("sync"):
        ctx = multiprocessing.get_context("spawn")
        with ctx.Lock():
            pass
    created = [e for e in rec.events() if e.event_type == E.LOCK_CREATED]
    assert len(created) == 1


def test_auto_sync_leaves_the_classes_so_plain_locks_still_pickle():
    import pickle

    with auto_instrument("sync"):
        # What a pool or executor does with its own locks.
        cls = multiprocessing.synchronize.Lock
        assert cls.__module__ == "multiprocessing.synchronize"
        assert pickle.dumps(cls)


def _by(rec, event_type):
    """Actors that emitted ``event_type``, in order, without repeats."""
    return list(
        dict.fromkeys(
            e.thread_id for e in rec.events() if e.event_type == event_type
        )
    )


def test_an_event_set_in_one_process_wakes_a_wait_in_another(rec):
    ready = concurim.TracedMPEvent(name="ready")
    run_children(
        (pool_tasks.wait_for_event, (ready,)),
        (pool_tasks.set_event, (ready,)),
    )
    (setter,) = _by(rec, E.EVENT_SET)
    (waiter,) = _by(rec, E.EVENT_WAIT_COMPLETED)
    assert setter != waiter
    r = replay_of(rec)
    assert r["warnings"] == [] and r["hazards"] == []
    state = world_after(r)["syncs"]["event-1"]
    assert state["kind"] == "event" and state["is_set"] is True


def test_a_barrier_shows_each_process_that_arrives(rec):
    gate = concurim.TracedMPBarrier(2, name="gate")
    run_children(*[(pool_tasks.meet, (gate,))] * 2)
    assert len(_by(rec, E.BARRIER_WAIT_COMPLETED)) == 2
    assert E.BARRIER_WAIT_BLOCKED in types(rec.events())
    r = replay_of(rec)
    assert r["warnings"] == []
    assert r["entities"]["syncs"]["barrier-1"]["capacity"] == 2


def test_plain_event_and_barrier_behave_the_same_without_recording():
    event = concurim.TracedMPEvent()
    assert not event.is_set() and event.wait(0.01) is False
    event.set()
    assert event.is_set() and event.wait(0.01) is True
    event.clear()
    assert not event.is_set()
    gate = concurim.TracedMPBarrier(1)
    assert gate.wait(1) == 0 and gate.parties == 1


def test_auto_sync_traces_events_and_barriers_made_by_user_code():
    with record(auto="sync") as rec:
        event = multiprocessing.Event()
        gate = multiprocessing.Barrier(1)
        event.set()
        gate.wait()
        multiprocessing.Queue().close()  # its internals stay plain
    created = [
        e.metadata["name"]
        for e in rec.events()
        if e.event_type in (E.EVENT_CREATED, E.BARRIER_CREATED)
    ]
    assert len(created) == 2 and all("(line " in n for n in created)
    assert len(_by(rec, E.EVENT_SET)) == 1
