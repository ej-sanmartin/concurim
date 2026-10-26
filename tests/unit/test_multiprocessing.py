"""multiprocessing.Pool and Process: tasks, workers, copied vs shared."""

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


def named(rec, event_type):
    return [e for e in rec.events() if e.event_type == event_type]


def test_pool_map_shows_one_task_per_item_on_worker_processes(rec):
    with concurim.TracedPool(2, context=SPAWN, name="Pool") as pool:
        assert pool.map(pool_tasks.square, range(5)) == [0, 1, 4, 9, 16]
    ev = types(rec.events(), "executor.")
    assert ev.count(E.EXECUTOR_SUBMIT) == 5
    assert ev.count(E.EXECUTOR_TASK_STARTED) == 5
    assert ev.count(E.EXECUTOR_TASK_FINISHED) == 5
    r = replay_of(rec)
    assert r["warnings"] == []
    procs = [
        t for t in r["entities"]["threads"].values() if t["kind"] == "process"
    ]
    assert 1 <= len(procs) <= 2
    end = world_after(r)
    assert all(
        t["status"] == "finished"
        for t in end["threads"].values()
        if t["kind"] == "process"
    )
    queue = next(iter(r["entities"]["queues"].values()))
    assert (queue["name"], queue["kind"]) == ("Pool", "executor")


def test_submissions_are_attributed_to_the_caller_even_for_imap(rec):
    with concurim.TracedPool(2, context=SPAWN) as pool:
        got = sorted(pool.imap_unordered(pool_tasks.square, range(4)))
    assert got == [0, 1, 4, 9]
    created = named(rec, E.EXECUTOR_CREATED)[0]
    submits = named(rec, E.EXECUTOR_SUBMIT)
    assert len(submits) == 4
    assert {e.thread_id for e in submits} == {created.thread_id}


def test_starmap_and_apply_async_are_recorded(rec):
    with concurim.TracedPool(1, context=SPAWN) as pool:
        assert pool.starmap(pool_tasks.add, [(1, 2), (3, 4)]) == [3, 7]
        assert pool.apply_async(pool_tasks.square, (6,)).get() == 36
    assert types(rec.events(), "executor.").count(E.EXECUTOR_SUBMIT) == 3
    assert replay_of(rec)["warnings"] == []


def test_a_failing_task_is_recorded_and_still_raises(rec):
    pool = concurim.TracedPool(1, context=SPAWN)
    with pool, pytest.raises(ValueError, match="bad 3"):
        pool.apply(pool_tasks.boom, (3,))
    failed = named(rec, E.EXECUTOR_TASK_FAILED)
    assert [e.metadata["error"] for e in failed] == ["ValueError"]


def test_arguments_are_marked_copied_and_results_are_sized(rec):
    items = [1, 2, 3]
    with concurim.TracedPool(1, context=SPAWN) as pool:
        assert pool.apply(pool_tasks.append_one, (items,)) == 4
    assert items == [1, 2, 3]  # the worker changed its own copy
    meta = named(rec, E.EXECUTOR_SUBMIT)[0].metadata
    assert (meta["copied_args"], meta["shared_args"]) == (1, 0)
    assert meta["copied_bytes"] > 0
    done = named(rec, E.EXECUTOR_TASK_FINISHED)[0].metadata
    assert done["result_bytes"] > 0
    text = replay_of(rec)["frames"][
        next(
            i
            for i, e in enumerate(rec.events())
            if e.event_type == E.EXECUTOR_SUBMIT
        )
    ]["explanation"]["text"]
    assert "copied" in text


def test_exiting_the_with_block_records_a_shutdown_without_dropping(rec):
    with concurim.TracedPool(1, context=SPAWN) as pool:
        pool.map(pool_tasks.square, [1, 2])
    shutdown = named(rec, E.EXECUTOR_SHUTDOWN)
    assert len(shutdown) == 1
    assert shutdown[0].metadata["cancel_futures"] is False


def test_process_records_start_work_and_end_with_shared_vs_copied(rec):
    counter = multiprocessing.Value("i", 0)
    items = [1]
    proc = concurim.TracedProcess(
        target=pool_tasks.bump, args=(counter, items), name="child"
    )
    proc.start()
    proc.join()
    assert counter.value == 1 and items == [1]
    ev = types(rec.events(), "thread.")
    assert E.THREAD_START_REQUESTED in ev and E.THREAD_FINISHED in ev
    request = named(rec, E.THREAD_START_REQUESTED)[0].metadata
    assert request["process"] is True
    assert request["shared_args"] == 1 and request["copied_args"] == 1
    assert request["shared_types"] == "Synchronized"
    r = replay_of(rec)
    assert r["warnings"] == []
    child = [
        t for t in r["entities"]["threads"].values() if t["kind"] == "process"
    ]
    assert len(child) == 1
    assert world_after(r)["threads"][child[0]["id"]]["status"] == "finished"


def test_a_failing_process_is_recorded_as_failed(rec):
    proc = concurim.TracedProcess(target=pool_tasks.boom, args=(1,))
    proc.start()
    proc.join()
    assert proc.exitcode == 1
    failed = named(rec, E.THREAD_FAILED)
    assert [e.metadata["error"] for e in failed] == ["ValueError"]


def test_outside_a_recording_they_are_plain():
    proc = concurim.TracedProcess(target=pool_tasks.square, args=(2,))
    proc.start()
    proc.join()
    assert proc.exitcode == 0 and not hasattr(proc, "_cz_sink")
    with concurim.TracedPool(1, context=SPAWN) as pool:
        assert pool.map(pool_tasks.square, [3]) == [9]
        assert pool._cz_sink is None


def test_auto_sync_level_patches_both_and_restores_them():
    original = (multiprocessing.Process, multiprocessing.Pool)
    with record(auto="sync") as rec:
        with multiprocessing.Pool(1) as pool:
            assert pool.map(pool_tasks.square, [2, 3]) == [4, 9]
        proc = multiprocessing.Process(target=pool_tasks.square, args=(1,))
        proc.start()
        proc.join()
    ev = types(rec.events())
    assert ev.count(E.EXECUTOR_SUBMIT) == 2
    assert E.THREAD_START_REQUESTED in ev
    with auto_instrument("sync"):
        assert multiprocessing.Pool is not original[1]
    assert (multiprocessing.Process, multiprocessing.Pool) == original
    assert replay_of(rec)["warnings"] == []
