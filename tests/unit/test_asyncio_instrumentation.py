"""asyncio: tasks, task switching, and the traced primitives."""

import asyncio
import contextlib

import concurim
from concurim.instrumentation.auto import auto_instrument
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import types, world_after


def run(main, auto="asyncio"):
    with record(auto=auto) as rec:
        asyncio.run(main())
    return rec


def replay_of(rec):
    return build_replay(Trace({"program": {}}, rec.events(), {}))


def names(r):
    return {t["name"]: t["id"] for t in r["entities"]["threads"].values()}


def test_only_one_task_runs_at_a_time_and_steps_pair_up():
    async def worker(n):
        for _ in range(3):
            await asyncio.sleep(0)

    async def main():
        await asyncio.gather(worker(1), worker(2))

    rec = run(main)
    open_step = None
    for e in rec.events():
        if e.event_type == E.TASK_STEP_STARTED:
            assert open_step is None, "two tasks ran at once"
            open_step = e.task_id
        elif e.event_type == E.TASK_STEP_ENDED:
            assert open_step == e.task_id
            open_step = None
    assert open_step is None
    r = replay_of(rec)
    assert r["warnings"] == []
    tasks = [
        t for t in r["entities"]["threads"].values() if t["kind"] == "task"
    ]
    assert len(tasks) == 3  # main + two workers
    final = world_after(r)["threads"]
    assert {final[t["id"]]["status"] for t in tasks} == {"finished"}


def test_suspended_tasks_are_shown_as_suspended_not_blocked():
    async def sleeper():
        await asyncio.sleep(0.05)

    async def main():
        t = asyncio.create_task(sleeper(), name="sleeper")
        await asyncio.sleep(0.01)
        # Mid-flight: the sleeper awaits something Concurim cannot see.
        mid = [
            e
            for e in concurim.active_recorder().events()
            if e.event_type == E.TASK_STEP_ENDED
        ]
        assert mid
        await t

    rec = run(main)
    r = replay_of(rec)
    sleeping = names(r)["sleeper"]
    statuses = [
        f["changes"]["threads"][sleeping]["status"]
        for f in r["frames"]
        if sleeping in f["changes"].get("threads", {})
    ]
    assert "suspended" in statuses and statuses[-1] == "finished"
    assert "waiting" not in statuses  # a sleep is not a traced wait


def test_asyncio_queue_blocks_a_task_not_the_loop():
    async def producer(q):
        for i in range(3):
            await q.put(i)

    async def consumer(q):
        for _ in range(3):
            await q.get()
            q.task_done()

    async def main():
        q = asyncio.Queue(maxsize=1)
        await asyncio.gather(
            asyncio.create_task(consumer(q), name="consumer"),
            asyncio.create_task(producer(q), name="producer"),
        )
        await q.join()

    rec = run(main)
    ev = types(rec.events(), "queue.")
    assert ev.count(E.QUEUE_PUT_COMPLETED) == 3
    assert ev.count(E.QUEUE_GET_COMPLETED) == 3
    assert E.QUEUE_GET_BLOCKED in ev  # the consumer starts first
    r = replay_of(rec)
    assert r["warnings"] == []
    blocked = [
        f["explanation"]["text"]
        for f in r["frames"]
        if f["explanation"]["title"] == "Get blocked"
    ]
    assert blocked and "consumer" in blocked[0]
    q = world_after(r)["queues"]["queue-1"]
    assert q["items"] == [] and q["unfinished"] == 0
    assert [s["thread"] for s in r["spans"] if s["kind"] == "wait_get"] == [
        names(r)["consumer"]
    ] * len(blocked)


def test_asyncio_lock_and_semaphore_wait_by_task():
    async def use(lock, sem):
        async with lock:
            await asyncio.sleep(0.005)
        async with sem:
            await asyncio.sleep(0.005)

    async def main():
        lock, sem = asyncio.Lock(), asyncio.Semaphore(2)
        await asyncio.gather(*(use(lock, sem) for _ in range(3)))

    rec = run(main)
    ev = types(rec.events())
    assert ev.count(E.LOCK_ACQUIRE_COMPLETED) == 3
    assert ev.count(E.SEMAPHORE_ACQUIRE_COMPLETED) == 3
    assert E.LOCK_ACQUIRE_BLOCKED in ev
    r = replay_of(rec)
    assert r["warnings"] == []
    final = world_after(r)["syncs"]
    assert all(
        s["holders"] == [] and s["waiters"] == [] for s in final.values()
    )
    assert final["semaphore-1"]["value"] == 2


def test_cancellation_is_recorded_for_the_task_and_its_wait():
    async def waiter(q):
        await q.get()

    async def main():
        q = asyncio.Queue()
        t = asyncio.create_task(waiter(q), name="waiter")
        await asyncio.sleep(0.01)
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t

    rec = run(main)
    failed = [e for e in rec.events() if e.event_type == E.QUEUE_GET_FAILED]
    assert failed[0].metadata["reason"] == "cancelled"
    r = replay_of(rec)
    cancelled = names(r)["waiter"]
    assert world_after(r)["threads"][cancelled]["status"] == "cancelled"
    assert world_after(r)["queues"]["queue-1"]["blocked_gets"] == []


def test_failed_task_keeps_asyncios_own_exception_reporting():
    async def boom():
        raise ValueError("expected")

    async def main():
        t = asyncio.create_task(boom(), name="boom")
        await asyncio.sleep(0.01)
        assert t.done()
        # Concurim must not have marked the exception as retrieved.
        assert t._log_traceback is True
        t.exception()

    rec = run(main)
    failed = [e for e in rec.events() if e.event_type == E.TASK_FAILED]
    assert failed[0].metadata["error"] == "ValueError"


def test_nowait_calls_and_plain_get_are_recorded_once():
    async def main():
        q = asyncio.Queue(maxsize=1)
        q.put_nowait("a")
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait("b")
        assert q.get_nowait() == "a"
        with contextlib.suppress(asyncio.QueueEmpty):
            q.get_nowait()

    rec = run(main)
    ev = types(rec.events(), "queue.")
    assert ev.count(E.QUEUE_PUT_COMPLETED) == 1
    assert ev.count(E.QUEUE_GET_COMPLETED) == 1
    assert ev.count(E.QUEUE_PUT_FAILED) == 1
    assert ev.count(E.QUEUE_GET_FAILED) == 1


def test_lower_levels_do_not_see_asyncio():
    async def main():
        q = asyncio.Queue()
        await q.put(1)

    rec = run(main, auto="sync")
    assert types(rec.events(), "task.") == []
    assert types(rec.events(), "queue.") == []


def test_patches_are_restored():
    originals = (asyncio.Queue, asyncio.Lock, asyncio.Handle._run)
    with auto_instrument("asyncio"):
        assert asyncio.Queue is not originals[0]
    assert (asyncio.Queue, asyncio.Lock, asyncio.Handle._run) == originals


def test_traced_async_classes_work_without_a_recording():
    async def main():
        q = concurim.TracedAsyncQueue(maxsize=1)
        lock = concurim.TracedAsyncLock()
        await q.put(1)
        async with lock:
            assert await q.get() == 1

    asyncio.run(main())
