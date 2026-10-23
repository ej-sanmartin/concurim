"""Scheduling-sensitive tests: many producers/consumers, varied timing.

No test asserts a specific interleaving. Each asserts invariants that must
hold for *every* schedule, and every thread join has a deadlock timeout.
"""

import contextlib
import queue
import random
import threading
import time

import pytest

import concurim
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import TIMEOUT, world_after

pytestmark = pytest.mark.concurrency


def pipeline(seed, producers, consumers, maxsize, per_producer, jitter):
    rng = random.Random(seed)
    delays = [rng.random() * jitter for _ in range(64)]
    received = []
    lock = threading.Lock()
    q = concurim.TracedQueue(maxsize=maxsize, name="Q")

    def producer(pid):
        for n in range(per_producer):
            time.sleep(delays[(pid * 7 + n) % 64])
            q.put((pid, n))

    def consumer(cid):
        while True:
            try:
                item = q.get_with_id()
            except queue.ShutDown:
                return
            time.sleep(delays[(cid * 13 + len(received)) % 64])
            with lock:
                received.append(item.value)
            q.task_done(object_id=item.object_id)

    cons = [
        concurim.TracedThread(target=consumer, args=(i,))
        for i in range(consumers)
    ]
    prods = [
        concurim.TracedThread(target=producer, args=(i,))
        for i in range(producers)
    ]
    for t in cons + prods:
        t.start()
    for t in prods:
        t.join(TIMEOUT)
        assert not t.is_alive(), "producer deadlocked"
    q.join()
    q.shutdown()
    for t in cons:
        t.join(TIMEOUT)
        assert not t.is_alive(), "consumer deadlocked"
    return received


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize(
    "shape",
    [
        (1, 1, 1, 6),
        (3, 2, 2, 8),
        (4, 4, 5, 6),
        (2, 5, 3, 10),
        (6, 1, 0, 5),
    ],
)
def test_pipeline_invariants_hold_for_any_schedule(seed, shape):
    producers, consumers, maxsize, per = shape
    with record() as rec:
        received = pipeline(seed, producers, consumers, maxsize, per, 0.003)
    # The program's own result is unchanged by instrumentation.
    expected = {(p, n) for p in range(producers) for n in range(per)}
    assert sorted(received) == sorted(expected)

    events = rec.events()
    assert rec.dropped == 0
    replay = build_replay(Trace({}, events))
    assert replay["warnings"] == []

    by_obj = {}
    for e in events:
        if e.event_type in (E.QUEUE_PUT_COMPLETED, E.QUEUE_GET_COMPLETED):
            by_obj.setdefault(e.object_id, {})[e.event_type] = e.sequence
    assert len(by_obj) == len(expected)
    for oid, seqs in by_obj.items():
        assert seqs[E.QUEUE_PUT_COMPLETED] < seqs[E.QUEUE_GET_COMPLETED], oid

    sizes = [o[1] for o in replay["occupancy"]["queue-1"]]
    if maxsize > 0:
        assert max(sizes) <= maxsize
    final = world_after(replay)["queues"]["queue-1"]
    assert final["items"] == [] and final["unfinished"] == 0
    assert final["shutdown"] == "graceful"


def test_recording_a_contended_queue_does_not_deadlock_the_collector():
    """Many threads hammer one tiny queue; the collector lock is taken under
    the queue mutex, so any lock-order mistake would hang here."""
    with record() as rec:
        q = concurim.TracedQueue(maxsize=1, name="hot")
        n_threads, per = 8, 200
        done = []

        def worker(i):
            for k in range(per):
                if i % 2:
                    q.put((i, k))
                else:
                    with contextlib.suppress(queue.Empty):
                        q.get(timeout=0.5)
            done.append(i)

        threads = [
            concurim.TracedThread(target=worker, args=(i,))
            for i in range(n_threads)
        ]
        for t in threads:
            t.start()
        # Drain so blocked producers can finish.
        deadline = time.monotonic() + 20
        while len(done) < n_threads and time.monotonic() < deadline:
            with contextlib.suppress(queue.Empty):
                q.get(timeout=0.01)
        for t in threads:
            t.join(TIMEOUT)
            assert not t.is_alive()
    assert len(done) == n_threads
    replay = build_replay(Trace({}, rec.events()))
    assert replay["warnings"] == []
