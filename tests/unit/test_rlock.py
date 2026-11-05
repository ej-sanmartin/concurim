"""RLock: owner and depth in the replay, and releases the lock refuses."""

import threading

import pytest

import concurim
from concurim.recorder.events import EventType as E
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import TIMEOUT, types, world_after


def replay_of(rec):
    return build_replay(Trace({"program": {}}, rec.events(), {}))


def explanations(replay, title):
    return [
        f["explanation"]["text"]
        for f in replay["frames"]
        if f["explanation"]["title"] == title
    ]


def test_re_entry_is_explained_with_its_depth(rec):
    lock = concurim.TracedRLock(name="R")
    with lock, lock:
        mid = replay_of(rec)
        assert world_after(mid)["syncs"]["lock-1"]["holders"] == [
            "thread-1",
            "thread-1",
        ]
    r = replay_of(rec)
    (text,) = explanations(r, "Re-entered")
    assert "held 2 deep" in text and "released 2 times" in text
    levels = explanations(r, "Released")
    assert "one level" in levels[0] and "1 deep" in levels[0]
    assert "one level" not in levels[1]
    assert r["warnings"] == [] and r["hazards"] == []


def test_a_new_rlock_is_described_as_reentrant(rec):
    concurim.TracedRLock(name="R")
    (text,) = explanations(replay_of(rec), "Lock created")
    assert "reentrant" in text


def test_releasing_an_rlock_nobody_holds_is_recorded_then_raises(rec):
    lock = concurim.TracedRLock(name="R")
    with pytest.raises(RuntimeError):
        lock.release()
    (failed,) = [
        e for e in rec.events() if e.event_type == E.LOCK_RELEASE_FAILED
    ]
    assert failed.metadata["reason"] == "not_acquired"
    assert E.LOCK_RELEASED not in types(rec.events())
    (text,) = explanations(replay_of(rec), "Release refused")
    assert "no thread held it" in text and "RuntimeError" in text


def test_releasing_another_threads_rlock_is_not_owner(rec):
    lock = concurim.TracedRLock(name="R")
    held, leave = threading.Event(), threading.Event()

    def owner():
        with lock:
            held.set()
            leave.wait(TIMEOUT)

    t = concurim.TracedThread(target=owner, name="owner")
    t.start()
    held.wait(TIMEOUT)
    with pytest.raises(RuntimeError):
        lock.release()
    leave.set()
    t.join(TIMEOUT)
    (failed,) = [
        e for e in rec.events() if e.event_type == E.LOCK_RELEASE_FAILED
    ]
    assert failed.metadata["reason"] == "not_owner"
    (text,) = explanations(replay_of(rec), "Release refused")
    assert "only the owner" in text
    # The refusal changed nothing: the owner's own release still pairs up.
    assert world_after(replay_of(rec))["syncs"]["lock-1"]["holders"] == []


def test_releasing_an_unlocked_plain_lock_is_recorded_then_raises(rec):
    lock = concurim.TracedLock(name="L")
    with pytest.raises(RuntimeError):
        lock.release()
    (failed,) = [
        e for e in rec.events() if e.event_type == E.LOCK_RELEASE_FAILED
    ]
    assert failed.metadata["reason"] == "not_locked"


def test_a_plain_lock_taken_twice_blocks_on_itself(rec):
    lock = concurim.TracedLock(name="L")
    lock.acquire()
    assert lock.acquire(timeout=0.02) is False
    lock.release()
    r = replay_of(rec)
    (text,) = explanations(r, "Acquire blocked on itself")
    assert "cannot be re-entered" in text and "RLock" in text


def test_an_rlock_taken_twice_never_blocks_on_itself(rec):
    lock = concurim.TracedRLock(name="R")
    with lock:
        assert lock.acquire(timeout=0.02) is True
        lock.release()
    r = replay_of(rec)
    assert explanations(r, "Acquire blocked on itself") == []
    assert E.LOCK_ACQUIRE_BLOCKED not in types(rec.events())
