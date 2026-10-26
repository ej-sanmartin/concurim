"""A lock cycle is reported from the events, and cleared when the waits end."""

import threading
import time

import concurim
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import TIMEOUT


def test_a_lock_cycle_is_named_and_then_clears(rec):
    lock_a = concurim.TracedLock(name="A")
    lock_b = concurim.TracedLock(name="B")
    held = [threading.Event(), threading.Event()]

    def take(first, second, mine, other):
        first.acquire()
        try:
            mine.set()
            assert other.wait(TIMEOUT)
            if second.acquire(timeout=0.3):
                second.release()
        finally:
            first.release()

    threads = [
        concurim.TracedThread(
            target=take,
            args=(lock_a, lock_b, held[0], held[1]),
            name="A-then-B",
        ),
        concurim.TracedThread(
            target=take,
            args=(lock_b, lock_a, held[1], held[0]),
            name="B-then-A",
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMEOUT)
        assert not thread.is_alive()

    replay = build_replay(Trace({"program": {}}, rec.events(), {}))
    wait = replay["wait_for"]
    assert wait["cycles"] == []
    assert wait["episodes"]
    episode = wait["episodes"][0]
    assert episode["resolved_at"] is not None
    assert set(episode["actors"][0]) == {"A-then-B", "B-then-A"}
    assert any("cleared" in warning for warning in replay["warnings"])
    # The event where the cycle appeared says so, and labels the inference.
    frame = replay["frames"][episode["at"]]
    assert "one another holds" in frame["explanation"]["text"]
    assert frame["explanation"]["inferred"]


def test_one_waiter_is_not_called_a_cycle(rec):
    lock = concurim.TracedLock(name="L")
    lock.acquire()
    started = threading.Event()

    def waiter():
        started.set()
        lock.acquire()
        lock.release()

    thread = concurim.TracedThread(target=waiter, name="waiter")
    thread.start()
    assert started.wait(TIMEOUT)
    time.sleep(0.05)
    replay = build_replay(Trace({"program": {}}, rec.events(), {}))
    assert replay["wait_for"]["cycles"] == []
    assert replay["wait_for"]["episodes"] == []
    lock.release()
    thread.join(TIMEOUT)
