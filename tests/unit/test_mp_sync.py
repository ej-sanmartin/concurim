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
