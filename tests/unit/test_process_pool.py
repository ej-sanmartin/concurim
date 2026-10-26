"""ProcessPoolExecutor: submissions in the parent, tasks in each worker."""

import concurrent.futures
import multiprocessing

import pool_tasks
import pytest

import concurim
from concurim.instrumentation.auto import auto_instrument
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import types, world_after

SPAWN = multiprocessing.get_context("spawn")


def replay_of(rec):
    return build_replay(Trace({"program": {}}, rec.events(), {}))


def test_tasks_are_attributed_to_one_actor_per_worker_process(rec):
    with concurim.TracedProcessPoolExecutor(
        2, mp_context=SPAWN, name="Pool"
    ) as pool:
        results = [pool.submit(pool_tasks.square, n).result() for n in range(4)]
    assert results == [0, 1, 4, 9]
    ev = types(rec.events(), "executor.")
    assert ev.count(E.EXECUTOR_SUBMIT) == 4
    assert ev.count(E.EXECUTOR_TASK_STARTED) == 4
    assert ev.count(E.EXECUTOR_TASK_FINISHED) == 4
    r = replay_of(rec)
    assert r["warnings"] == []
    workers = [t for t in r["entities"]["threads"].values()]
    procs = [t for t in workers if t["kind"] == "process"]
    assert 1 <= len(procs) <= 2
    assert all(t["name"].startswith("SpawnProcess") for t in procs)
    pool = next(iter(r["entities"]["queues"].values()))
    assert (pool["name"], pool["kind"], pool["workers"]) == (
        "Pool",
        "executor",
        2,
    )
    end = world_after(r)
    assert end["queues"]["executor-1"]["running"] == 0
    assert all(
        t["status"] == "finished"
        for t in end["threads"].values()
        if t["kind"] == "process"
    )


def test_started_precedes_finished_and_follows_submit(rec):
    with concurim.TracedProcessPoolExecutor(1, mp_context=SPAWN) as pool:
        pool.submit(pool_tasks.square, 3).result()
    ev = types(rec.events(), "executor.")
    assert ev.index(E.EXECUTOR_SUBMIT) < ev.index(E.EXECUTOR_TASK_STARTED)
    assert ev.index(E.EXECUTOR_TASK_STARTED) < ev.index(
        E.EXECUTOR_TASK_FINISHED
    )
    started = next(
        e for e in rec.events() if e.event_type == E.EXECUTOR_TASK_STARTED
    )
    assert started.metadata["worker_pid"] != rec.process_id


def test_a_failing_task_is_recorded_and_still_raises(rec):
    with concurim.TracedProcessPoolExecutor(1, mp_context=SPAWN) as pool:
        future = pool.submit(pool_tasks.boom, 1)
        with pytest.raises(ValueError, match="bad 1"):
            future.result()
    failed = [e for e in rec.events() if e.event_type == E.EXECUTOR_TASK_FAILED]
    assert [e.metadata["error"] for e in failed] == ["ValueError"]
    assert replay_of(rec)["warnings"] == []


def test_map_names_tasks_after_the_users_function(rec):
    with concurim.TracedProcessPoolExecutor(2, mp_context=SPAWN) as pool:
        assert list(pool.map(pool_tasks.square, range(5))) == [0, 1, 4, 9, 16]
    names = {
        e.metadata["name"]
        for e in rec.events()
        if e.event_type == E.EXECUTOR_SUBMIT
    }
    assert names == {"square"}


def test_users_initializer_still_runs_in_workers(rec):
    with concurim.TracedProcessPoolExecutor(
        1,
        mp_context=SPAWN,
        initializer=pool_tasks.set_greeting,
        initargs=("hello",),
    ) as pool:
        assert pool.submit(pool_tasks.greeting, 0).result() == "hello"


def test_workers_are_marked_finished_when_the_pool_shuts_down(rec):
    with concurim.TracedProcessPoolExecutor(2, mp_context=SPAWN) as pool:
        list(pool.map(pool_tasks.pid, range(4)))
    ends = types(rec.events(), "thread.finished")
    assert len(ends) >= 1


def test_outside_a_recording_it_is_a_plain_process_pool():
    with concurim.TracedProcessPoolExecutor(1, mp_context=SPAWN) as pool:
        assert pool.submit(pool_tasks.square, 5).result() == 25
        assert pool._cz_sink is None


def test_auto_level_traces_pools_made_by_user_code_without_noise():
    pool_cls = concurrent.futures.ProcessPoolExecutor
    with record() as rec, auto_instrument("sync"):
        assert concurrent.futures.ProcessPoolExecutor is not pool_cls
        with concurrent.futures.ProcessPoolExecutor(
            2, mp_context=SPAWN
        ) as pool:
            list(pool.map(pool_tasks.square, range(3)))
    assert concurrent.futures.ProcessPoolExecutor is pool_cls  # restored
    r = replay_of(rec)
    assert r["warnings"] == []
    # No stdlib work queue and no manager/feeder/drain threads.
    assert [q["kind"] for q in r["entities"]["queues"].values()] == ["executor"]
    names = [t["name"] for t in r["entities"]["threads"].values()]
    assert "MainThread" in names
    assert not any("Feeder" in n or "_cz_drain" in n for n in names)
