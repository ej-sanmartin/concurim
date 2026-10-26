"""threading and asyncio barriers: arrivals, release, abort and reset."""

import asyncio
import contextlib
import threading

import concurim
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import run_threads, types, wait_for, world_after


def replay_of(rec):
    return build_replay(Trace({"program": {}}, rec.events(), {}))


def test_the_last_arrival_releases_everyone(rec):
    bar = concurim.TracedBarrier(2, name="Meet")
    order = []

    def first():
        order.append(bar.wait(5))

    def second():
        wait_for(lambda: E.BARRIER_WAIT_BLOCKED in types(rec.events()))
        order.append(bar.wait(5))

    run_threads(first, second)
    assert sorted(order) == [0, 1]
    replay = replay_of(rec)
    assert replay["warnings"] == []
    blocked = [
        e for e in rec.events() if e.event_type == E.BARRIER_WAIT_BLOCKED
    ]
    assert len(blocked) == 1
    assert any(
        s["kind"] == "wait_barrier" and s["outcome"] == "completed"
        for s in replay["spans"]
    )
    state = world_after(replay)["syncs"]["barrier-1"]
    assert state["waiters"] == [] and state["broken"] is False
    titles = [f["explanation"]["title"] for f in replay["frames"]]
    assert "Arrival waiting" in titles and "Barrier released" in titles


def test_abort_wakes_the_waiter_as_broken(rec):
    bar = concurim.TracedBarrier(2, name="Meet")
    errors = []

    def waiter():
        try:
            bar.wait(5)
        except threading.BrokenBarrierError:
            errors.append("broken")

    def aborter():
        wait_for(lambda: E.BARRIER_WAIT_BLOCKED in types(rec.events()))
        bar.abort()

    run_threads(waiter, aborter)
    assert errors == ["broken"]
    kinds = types(rec.events(), "barrier.")
    assert kinds.index(E.BARRIER_ABORT) < kinds.index(E.BARRIER_WAIT_FAILED)
    state = world_after(replay_of(rec))["syncs"]["barrier-1"]
    assert state["broken"] is True and state["waiters"] == []


def test_reset_lets_a_new_party_start(rec):
    bar = concurim.TracedBarrier(2, name="Meet")

    def waiter():
        with contextlib.suppress(threading.BrokenBarrierError):
            bar.wait(5)

    def resetter():
        wait_for(lambda: E.BARRIER_WAIT_BLOCKED in types(rec.events()))
        bar.reset()

    run_threads(waiter, resetter)
    arrived = []

    def again():
        arrived.append(bar.wait(5))

    run_threads(again, again)
    assert sorted(arrived) == [0, 1]
    state = world_after(replay_of(rec))["syncs"]["barrier-1"]
    assert state["broken"] is False


def test_plain_barrier_is_traced_and_its_condition_is_not():
    with record(auto="sync") as recorded:
        bar = threading.Barrier(1)
        assert bar.wait(1) == 0
    kinds = types(recorded.events())
    assert E.BARRIER_CREATED in kinds
    assert E.CONDITION_CREATED not in kinds


def test_asyncio_barrier_suspends_until_the_party_is_complete():
    async def main():
        bar = asyncio.Barrier(2)

        async def one():
            await bar.wait()

        task = asyncio.create_task(one())
        await asyncio.sleep(0.01)
        await bar.wait()
        await task

    with record(auto="asyncio") as rec:
        asyncio.run(main())
    replay = replay_of(rec)
    assert replay["warnings"] == []
    syncs = [
        s
        for s in replay["entities"]["syncs"].values()
        if s["kind"] == "barrier"
    ]
    assert len(syncs) == 1 and syncs[0]["capacity"] == 2
    assert E.BARRIER_WAIT_BLOCKED in types(rec.events())


def test_asyncio_abort_breaks_the_waiting_task():
    async def main():
        bar = asyncio.Barrier(2)

        async def one():
            try:
                await bar.wait()
            except asyncio.BrokenBarrierError:
                return "broken"
            return "ok"

        task = asyncio.create_task(one())
        await asyncio.sleep(0.01)
        await bar.abort()
        return await task

    with record(auto="asyncio") as rec:
        assert asyncio.run(main()) == "broken"
    kinds = types(rec.events(), "barrier.")
    assert kinds.index(E.BARRIER_ABORT) < kinds.index(E.BARRIER_WAIT_FAILED)
    state = world_after(replay_of(rec))["syncs"]
    barrier = next(s for s in state.values() if s["kind"] == "barrier")
    assert barrier["broken"] is True and barrier["waiters"] == []
