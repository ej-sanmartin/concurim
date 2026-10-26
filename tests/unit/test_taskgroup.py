"""asyncio.TaskGroup: members, the waiting parent, and failure."""

import asyncio

from concurim.instrumentation.auto import auto_instrument
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import types, world_after


def replay_of(rec):
    return build_replay(Trace({"program": {}}, rec.events(), {}))


def run(main):
    with record(auto="asyncio") as rec:
        try:
            asyncio.run(main())
        except BaseException as error:  # noqa: BLE001 - tests inspect it
            rec.error = error
    return rec


def test_members_are_recorded_and_the_parent_waits_for_them():
    async def child(n):
        await asyncio.sleep(0.02 * n)

    async def main():
        async with asyncio.TaskGroup() as tg:
            tg.create_task(child(1), name="a")
            tg.create_task(child(2), name="b")

    rec = run(main)
    ev = types(rec.events(), "taskgroup.")
    assert ev == [
        E.TASKGROUP_CREATED,
        E.TASKGROUP_TASK_ADDED,
        E.TASKGROUP_TASK_ADDED,
        E.TASKGROUP_EXIT_STARTED,
        E.TASKGROUP_EXIT_COMPLETED,
    ]
    r = replay_of(rec)
    assert r["warnings"] == []
    group = next(
        s for s in r["entities"]["syncs"].values() if s["kind"] == "taskgroup"
    )
    exit_at = next(
        i
        for i, e in enumerate(r["events"])
        if e["event_type"] == E.TASKGROUP_EXIT_STARTED
    )
    mid = world_after(r, exit_at)
    state = mid["syncs"][group["id"]]
    assert len(state["members"]) == 2 and state["running"] == 2
    parent = mid["threads"][r["events"][exit_at]["task_id"]]
    assert parent["status"] == "waiting"
    assert parent["waiting_on"]["resource"] == group["id"]
    end = world_after(r)["syncs"][group["id"]]
    assert end["running"] == 0 and end["waiters"] == []
    assert [s["kind"] for s in r["spans"]].count("wait_taskgroup") == 1


def test_a_failing_child_cancels_its_sibling_and_is_reported():
    async def boom():
        await asyncio.sleep(0.01)
        raise ValueError("expected in this test")

    async def slow():
        await asyncio.sleep(5)

    async def main():
        async with asyncio.TaskGroup() as tg:
            tg.create_task(boom(), name="boom")
            tg.create_task(slow(), name="slow")

    rec = run(main)
    assert isinstance(rec.error, ExceptionGroup)
    ev = types(rec.events())
    assert E.TASK_FAILED in ev and E.TASK_CANCELLED in ev
    done = [
        e for e in rec.events() if e.event_type == E.TASKGROUP_EXIT_COMPLETED
    ]
    assert done[0].metadata["error"] == "ExceptionGroup"
    r = replay_of(rec)
    assert r["warnings"] == []
    group = next(
        s for s in r["entities"]["syncs"].values() if s["kind"] == "taskgroup"
    )
    assert world_after(r)["syncs"][group["id"]]["running"] == 0
    spans = [s for s in r["spans"] if s["kind"] == "wait_taskgroup"]
    assert spans and spans[0]["outcome"] == "failed"


def test_an_error_in_the_block_body_is_recorded():
    async def child():
        await asyncio.sleep(5)

    async def main():
        async with asyncio.TaskGroup() as tg:
            tg.create_task(child())
            raise KeyError("body failed")

    rec = run(main)
    started = [
        e for e in rec.events() if e.event_type == E.TASKGROUP_EXIT_STARTED
    ]
    assert started[0].metadata["body_error"] == "KeyError"
    assert replay_of(rec)["warnings"] == []


def test_it_is_plain_outside_a_recording_and_patches_are_restored():
    original = asyncio.TaskGroup

    async def main():
        async with asyncio.TaskGroup() as tg:
            task = tg.create_task(asyncio.sleep(0, "ok"))
        return task.result()

    assert asyncio.run(main()) == "ok"
    with auto_instrument("asyncio"):
        assert asyncio.TaskGroup is not original
    assert asyncio.TaskGroup is original


def test_an_empty_group_does_not_wait():
    async def main():
        async with asyncio.TaskGroup():
            pass

    rec = run(main)
    r = replay_of(rec)
    assert r["warnings"] == []
    assert E.TASKGROUP_EXIT_COMPLETED in types(rec.events())
