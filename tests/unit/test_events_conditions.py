"""threading/asyncio Event and Condition: recorded accurately and honestly."""

import asyncio
import threading

import pytest

import concurim
from concurim.instrumentation.auto import auto_instrument
from concurim.recorder.environment import coverage_for
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import run_threads, types, wait_for, world_after


def replay_of(rec):
    return build_replay(Trace({"program": {}}, rec.events(), {}))


def syncs(r, kind):
    return [s for s in r["entities"]["syncs"].values() if s["kind"] == kind]


def test_event_wait_blocks_until_set_and_set_precedes_the_wakeup(rec):
    ev = concurim.TracedEvent(name="Go")
    woke = []

    def waiter():
        woke.append(ev.wait(5))

    def setter():
        wait_for(lambda: E.EVENT_WAIT_BLOCKED in types(rec.events()))
        ev.set()

    run_threads(waiter, setter)
    assert woke == [True]
    kinds = types(rec.events(), "event.")
    assert kinds.index(E.EVENT_SET) < kinds.index(E.EVENT_WAIT_COMPLETED)
    r = replay_of(rec)
    assert r["warnings"] == []
    assert [s["kind"] for s in r["spans"]] == ["wait_event"]
    state = world_after(r)["syncs"][syncs(r, "event")[0]["id"]]
    assert state["is_set"] and state["waiters"] == []


def test_wait_on_a_set_event_never_blocks(rec):
    ev = concurim.TracedEvent()
    ev.set()
    assert ev.wait(1) is True
    assert E.EVENT_WAIT_BLOCKED not in types(rec.events())
    assert types(rec.events(), "event.wait") == [
        E.EVENT_WAIT_STARTED,
        E.EVENT_WAIT_COMPLETED,
    ]


def test_event_wait_timeout_is_recorded_and_clear_resets(rec):
    ev = concurim.TracedEvent()
    assert ev.wait(0.01) is False
    ev.set()
    ev.clear()
    ev.clear()
    ev_types = types(rec.events(), "event.")
    assert E.EVENT_WAIT_TIMEOUT in ev_types
    r = replay_of(rec)
    assert world_after(r)["syncs"]["event-1"]["is_set"] is False
    titles = [f["explanation"]["title"] for f in r["frames"]]
    assert "Wait timed out" in titles


def test_condition_wait_releases_lock_and_notify_does_not(rec):
    cond = concurim.TracedCondition(name="C")
    items = []
    got = []

    def consumer():
        with cond:
            while not items:
                cond.wait(5)
            got.append(items.pop())

    def producer():
        wait_for(lambda: E.CONDITION_WAIT_STARTED in types(rec.events()))
        with cond:
            items.append(7)
            cond.notify()
            # Still the holder: the notification did not release the lock.
            r = replay_of(rec)
            lock = world_after(r)["syncs"]["lock-1"]
            assert len(lock["holders"]) == 1

    run_threads(consumer, producer)
    assert got == [7]
    ev = types(rec.events())
    # wait: release, ..., notify, release (by producer), re-acquire, woken.
    assert ev.index(E.CONDITION_NOTIFY) < ev.index(E.CONDITION_WAIT_COMPLETED)
    woken_at = ev.index(E.CONDITION_WAIT_COMPLETED)
    assert (
        E.LOCK_ACQUIRE_COMPLETED in ev[ev.index(E.CONDITION_NOTIFY) : woken_at]
    )
    r = replay_of(rec)
    assert r["warnings"] == []
    cond_state = world_after(r)["syncs"]["condition-1"]
    assert cond_state["waiters"] == [] and cond_state["notified"] == 0
    assert cond_state["lock"] == "lock-1"
    assert [s["kind"] for s in r["spans"]].count("wait_condition") == 1


def test_notify_all_counts_waiters_without_naming_who_wakes(rec):
    cond = concurim.TracedCondition()
    ready = []

    def waiter():
        with cond:
            cond.wait_for(lambda: ready, 5)

    def waker():
        wait_for(
            lambda: types(rec.events()).count(E.CONDITION_WAIT_STARTED) >= 2
        )
        with cond:
            ready.append(1)
            cond.notify_all()

    run_threads(waiter, waiter, waker)
    notify = [e for e in rec.events() if e.event_type == E.CONDITION_NOTIFY][0]
    assert notify.metadata["all"] is True and notify.metadata["woken"] == 2
    r = replay_of(rec)
    text = next(
        f["explanation"]["text"]
        for f, e in zip(r["frames"], r["events"])
        if e["event_type"] == E.CONDITION_NOTIFY
    )
    assert "not guaranteed" in text


def test_condition_with_recursively_held_rlock_releases_all_levels(rec):
    cond = concurim.TracedCondition()
    entered = threading.Event()  # plain: not recorded
    done = threading.Event()

    def deep_waiter():
        with cond, cond:
            entered.set()
            cond.wait(5)
        done.set()

    t = concurim.TracedThread(target=deep_waiter)
    t.start()
    entered.wait(5)
    wait_for(lambda: E.CONDITION_WAIT_STARTED in types(rec.events()))
    with cond:  # would deadlock if only one level had been released
        cond.notify()
    t.join(5)
    assert done.is_set()
    r = replay_of(rec)
    assert r["warnings"] == []
    assert world_after(r)["syncs"]["lock-1"]["holders"] == []


def test_traced_lock_under_a_condition_adds_no_phantom_acquires(rec):
    cond = concurim.TracedCondition(concurim.TracedLock(name="L"))
    with cond:
        cond.notify()  # asks "is it owned?" without a real acquire
    acquires = types(rec.events(), "lock.acquire.")
    assert acquires == [E.LOCK_ACQUIRE_STARTED, E.LOCK_ACQUIRE_COMPLETED]


def test_condition_without_the_lock_still_raises():
    with record():
        cond = concurim.TracedCondition()
        with pytest.raises(RuntimeError):
            cond.wait(0.01)
        with pytest.raises(RuntimeError):
            cond.notify()


def test_outside_a_recording_they_are_plain():
    ev = concurim.TracedEvent()
    assert ev.wait(0.001) is False
    ev.set()
    assert ev.wait(0.001) is True
    cond = concurim.TracedCondition()
    with cond:
        assert cond.wait(0.001) is False
        cond.notify_all()


def test_sync_level_traces_user_made_events_not_the_librarys():
    with record(auto="sync") as rec:
        ev = threading.Event()
        cond = threading.Condition()
        t = threading.Thread(target=ev.set)  # Thread makes its own Event
        t.start()
        t.join(5)
        assert ev.wait(5)
        with cond:
            cond.notify()
    r = replay_of(rec)
    assert len(syncs(r, "event")) == 1
    assert len(syncs(r, "condition")) == 1
    assert threading.Event is not concurim.TracedEvent


def test_patches_are_restored():
    event, condition = threading.Event, threading.Condition
    aio_event, aio_condition = asyncio.Event, asyncio.Condition
    with auto_instrument("asyncio"):
        assert threading.Event is not event
        assert asyncio.Condition is not aio_condition
    assert threading.Event is event and threading.Condition is condition
    assert asyncio.Event is aio_event and asyncio.Condition is aio_condition


def test_asyncio_event_suspends_the_waiting_task_only():
    async def waiter(ev):
        await ev.wait()

    async def main():
        ev = asyncio.Event()
        t = asyncio.create_task(waiter(ev), name="waiter")
        await asyncio.sleep(0.01)
        ev.set()
        await t

    with record(auto="asyncio") as rec:
        asyncio.run(main())
    r = replay_of(rec)
    assert r["warnings"] == []
    kinds = types(rec.events(), "event.")
    assert kinds == [
        E.EVENT_CREATED,
        E.EVENT_WAIT_STARTED,
        E.EVENT_WAIT_BLOCKED,
        E.EVENT_SET,
        E.EVENT_WAIT_COMPLETED,
    ]
    waiter_id = next(
        t["id"]
        for t in r["entities"]["threads"].values()
        if t["name"] == "waiter"
    )
    waits = [e for e in rec.events() if e.event_type.startswith("event.wait")]
    assert {e.task_id for e in waits} == {waiter_id}


def test_asyncio_condition_notify_then_reacquire():
    async def consumer(cond, items):
        async with cond:
            await cond.wait_for(lambda: items)

    async def main():
        cond = asyncio.Condition()
        items = []
        t = asyncio.create_task(consumer(cond, items), name="consumer")
        await asyncio.sleep(0.01)
        async with cond:
            items.append(1)
            cond.notify()
        await t

    with record(auto="asyncio") as rec:
        asyncio.run(main())
    r = replay_of(rec)
    assert r["warnings"] == []
    ev = types(rec.events())
    assert ev.index(E.CONDITION_NOTIFY) < ev.index(E.CONDITION_WAIT_COMPLETED)
    state = world_after(r)["syncs"]["condition-1"]
    assert state["waiters"] == [] and state["lock"] == "lock-1"


def test_cancelled_wait_is_a_failure_not_a_wakeup():
    async def waiter(ev):
        await ev.wait()

    async def main():
        ev = asyncio.Event()
        t = asyncio.create_task(waiter(ev))
        await asyncio.sleep(0.01)
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)

    with record(auto="asyncio") as rec:
        asyncio.run(main())
    failed = [e for e in rec.events() if e.event_type == E.EVENT_WAIT_FAILED]
    assert failed and failed[0].metadata["reason"] == "cancelled"
    assert replay_of(rec)["warnings"] == []


def test_coverage_statement_mentions_events_at_the_right_levels():
    assert any("Event" in x for x in coverage_for("sync")["observed"])
    assert not any(
        "Event and Condition" in x for x in coverage_for("sync")["not_observed"]
    )
    assert any("events" in x for x in coverage_for("none")["not_observed"])
