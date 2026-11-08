"""Tracked shared values: access events, values over time, lockset races."""

import threading

import concurim
from concurim.config import RecorderConfig
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import TIMEOUT, run_threads, types, world_after


def replay_of(rec):
    return build_replay(Trace({"program": {}}, rec.events(), {}))


def races(replay):
    return [h for h in replay["hazards"] if h["kind"] == "unprotected_value"]


def test_an_increment_is_a_read_then_a_write(rec):
    cell = concurim.TracedCell(0, name="count")
    cell.value += 1
    assert cell.value == 1
    assert types(rec.events(), "cell.") == [
        E.CELL_CREATED,
        E.CELL_READ,
        E.CELL_WRITE,
        E.CELL_READ,
    ]


def test_it_is_a_plain_value_outside_a_recording():
    cell = concurim.TracedCell(5)
    cell.value += 1
    cell.set(cell.get() + 1)
    assert cell.value == 7


def test_the_replay_shows_the_value_and_who_held_which_lock():
    with record(config=RecorderConfig(preview=True)) as rec:
        cell = concurim.TracedCell(0, name="count")
        lock = concurim.TracedLock(name="L")
        with lock:
            cell.value = 3
        cell.value = 4
    r = replay_of(rec)
    texts = [f["explanation"]["text"] for f in r["frames"]]
    assert any("from 0 to 3" in t and "holding L" in t for t in texts)
    assert any("from 3 to 4" in t and "holding no lock" in t for t in texts)
    state = world_after(r)["syncs"]["cell-1"]
    assert state["kind"] == "cell" and state["preview"] == "4"
    assert [a["op"] for a in state["accesses"]] == ["write", "write"]
    assert state["accesses"][0]["locks"] == ["lock-1"]
    assert state["accesses"][1]["locks"] == []


def test_the_value_stays_private_unless_previews_are_on(rec):
    cell = concurim.TracedCell("secret", name="token")
    cell.value = "other"
    r = replay_of(rec)
    assert "secret" not in str(r["frames"]) and "other" not in str(r["frames"])
    assert world_after(r)["syncs"]["cell-1"]["preview"] is None


def test_two_threads_writing_with_no_lock_are_flagged(rec):
    cell = concurim.TracedCell(0, name="count")
    gate = threading.Barrier(2)

    def bump():
        gate.wait(TIMEOUT)
        cell.value += 1

    run_threads(bump, bump)
    found = races(replay_of(rec))
    assert len(found) == 1 and found[0]["inferred"] is True
    assert "no lock in common" in found[0]["text"]
    assert "not proof" in found[0]["text"]


def test_a_common_lock_protects_the_value(rec):
    cell = concurim.TracedCell(0, name="count")
    lock = concurim.TracedLock(name="L")

    def bump():
        with lock:
            cell.value += 1

    run_threads(bump, bump, bump)
    assert races(replay_of(rec)) == []


def test_different_locks_for_the_same_value_are_flagged(rec):
    cell = concurim.TracedCell(0, name="count")
    one, two = concurim.TracedLock(name="one"), concurim.TracedLock(name="two")

    def bump(lock):
        with lock:
            cell.value += 1

    run_threads(lambda: bump(one), lambda: bump(two))
    found = races(replay_of(rec))
    assert len(found) == 1
    assert "held one" in found[0]["text"] and "held two" in found[0]["text"]


def test_unlocked_set_up_before_sharing_is_not_a_race(rec):
    cell = concurim.TracedCell(0, name="count")
    cell.value = 10  # exclusive: only the main thread has touched it
    lock = concurim.TracedLock(name="L")

    def read_it():
        with lock:
            assert cell.value >= 10

    run_threads(read_it, read_it)
    assert races(replay_of(rec)) == []


def test_read_only_sharing_is_not_a_race(rec):
    cell = concurim.TracedCell(7, name="config")
    run_threads(lambda: cell.value, lambda: cell.value)
    assert races(replay_of(rec)) == []


def test_reading_the_result_after_the_workers_ended_is_not_a_race(rec):
    cell = concurim.TracedCell(0, name="count")
    lock = concurim.TracedLock(name="L")

    def bump():
        with lock:
            cell.value += 1

    run_threads(bump, bump)
    assert cell.value == 2  # no lock, but nobody else is running any more
    assert races(replay_of(rec)) == []


def test_reading_while_a_worker_still_writes_is_a_race(rec):
    cell = concurim.TracedCell(0, name="count")
    lock = concurim.TracedLock(name="L")
    wrote, leave = threading.Event(), threading.Event()

    def bump():
        with lock:
            cell.value += 1
        wrote.set()
        leave.wait(TIMEOUT)  # still running while the main thread reads

    t = concurim.TracedThread(target=bump)
    t.start()
    wrote.wait(TIMEOUT)
    assert cell.value == 1  # no lock, and the worker has not ended
    found = races(replay_of(rec))
    leave.set()
    t.join(TIMEOUT)
    assert len(found) == 1


def _hand_off(rec, send, take):
    """Run two threads: ``send`` first, then ``take``, ordered by the pair."""
    cell = concurim.TracedCell(0, name="count")
    run_threads(lambda: send(cell), lambda: take(cell))
    return races(replay_of(rec))


def test_a_value_passed_through_a_queue_is_not_a_race(rec):
    q = concurim.TracedQueue(name="Q")

    def send(cell):
        cell.value = 1  # no lock: the queue hands the value over
        q.put("ready")

    def take(cell):
        q.get()
        cell.value += 1

    assert _hand_off(rec, send, take) == []


def test_the_same_writes_with_no_hand_off_are_a_race(rec):
    gate = threading.Barrier(2)  # plain: Concurim does not see a barrier

    def send(cell):
        cell.value = 1
        gate.wait(TIMEOUT)

    def take(cell):
        gate.wait(TIMEOUT)
        cell.value += 1

    assert len(_hand_off(rec, send, take)) == 1


def test_a_value_passed_through_an_event_is_not_a_race(rec):
    ready = concurim.TracedEvent(name="ready")

    def send(cell):
        cell.value = 1
        ready.set()

    def take(cell):
        assert ready.wait(TIMEOUT)
        cell.value += 1

    assert _hand_off(rec, send, take) == []


def test_a_value_passed_through_a_lock_is_not_a_race(rec):
    lock = concurim.TracedLock(name="L")
    done = threading.Event()  # plain: forces the order, adds no edge

    def send(cell):
        cell.value = 1
        with lock:
            pass
        done.set()

    def take(cell):
        assert done.wait(TIMEOUT)
        with lock:
            pass  # taking the lock after the writer released it
        cell.value += 1  # but not holding it here

    assert _hand_off(rec, send, take) == []


def test_a_thread_starts_knowing_what_its_parent_wrote(rec):
    cell = concurim.TracedCell(0, name="count")
    cell.value = 10  # no lock, before the thread exists

    def child():
        cell.value += 1  # no lock either

    run_threads(child)
    assert races(replay_of(rec)) == []


def test_a_third_actor_with_no_hand_off_is_still_a_race(rec):
    q = concurim.TracedQueue(name="Q")
    gate = threading.Barrier(3)  # keeps all three alive together

    def send(cell):
        cell.value = 1
        q.put("ready")
        gate.wait(TIMEOUT)

    def take(cell):
        q.get()
        cell.value += 1
        gate.wait(TIMEOUT)

    def stray(cell):
        gate.wait(TIMEOUT)
        cell.value = 99

    cell = concurim.TracedCell(0, name="count")
    run_threads(lambda: send(cell), lambda: take(cell), lambda: stray(cell))
    assert len(races(replay_of(rec))) == 1
