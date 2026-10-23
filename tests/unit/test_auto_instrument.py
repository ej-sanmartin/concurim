"""Automatic instrumentation: reversible, accurate, and honest."""

import queue
import threading

import pytest

import concurim
from concurim.instrumentation.auto import auto_instrument
from concurim.recorder.environment import coverage_for
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay
from conftest import TIMEOUT, types


def join(*threads):
    for t in threads:
        t.join(TIMEOUT)
        assert not t.is_alive(), "thread did not finish"


def test_unknown_level_is_rejected():
    with pytest.raises(ValueError), auto_instrument("everything"):
        pass
    with pytest.raises(ValueError):
        concurim.RecorderConfig(auto="everything")


def test_patches_are_restored_even_when_the_program_fails():
    start, original_queue = threading.Thread.start, queue.Queue
    with pytest.raises(RuntimeError), auto_instrument("queues"):
        assert queue.Queue is not original_queue
        assert threading.Thread.start is not start
        raise RuntimeError("program failed")
    assert threading.Thread.start is start
    assert queue.Queue is original_queue


def test_level_none_does_not_observe_plain_threads():
    with record(auto="none") as rec:
        t = threading.Thread(target=lambda: None)
        t.start()
        join(t)
    assert types(rec.events(), "thread.") == []


@pytest.mark.filterwarnings(
    "ignore::pytest.PytestUnhandledThreadExceptionWarning"
)  # the failing thread is the point of the test
def test_threads_level_observes_plain_threads_and_run_overrides():
    class Worker(threading.Thread):
        def run(self):  # overrides run without calling super().run()
            pass

    def boom():
        raise ValueError("expected in this test")

    with record(auto="threads") as rec:
        plain = threading.Thread(target=lambda: None, name="plain")
        sub = Worker(name="sub")
        bad = threading.Thread(target=boom, name="bad")
        for t in (plain, sub, bad):
            t.start()
        join(plain, sub, bad)
    events = rec.events()
    assert types(events, "thread.").count(E.THREAD_STARTED) == 3
    assert types(events, "thread.").count(E.THREAD_FINISHED) == 2
    failed = [e for e in events if e.event_type == E.THREAD_FAILED]
    assert [e.metadata["error"] for e in failed] == ["ValueError"]
    # Queues are untouched at this level.
    assert queue.Queue.__module__ == "queue"
    assert not types(events, "queue.")


def test_threads_level_does_not_double_count_traced_threads():
    with record(auto="threads") as rec:
        t = concurim.TracedThread(target=lambda: None)
        t.start()
        join(t)
    assert types(rec.events(), "thread.").count(E.THREAD_STARTED) == 1


def test_queues_level_observes_plain_queue_and_replays_cleanly():
    with record(auto="queues") as rec:
        q = queue.Queue(maxsize=2)  # created during the recording
        got = []

        def consumer():
            for _ in range(5):
                got.append(q.get())
                q.task_done()

        c = threading.Thread(target=consumer)
        c.start()
        for n in range(5):
            q.put(n)
        q.join()
        join(c)
    assert got == [0, 1, 2, 3, 4]  # the program's behavior is unchanged
    events = rec.events()
    assert types(events, "queue.").count(E.QUEUE_PUT_COMPLETED) == 5
    assert types(events, "queue.").count(E.QUEUE_GET_COMPLETED) == 5
    replay = build_replay(Trace({}, events))
    assert replay["warnings"] == []
    assert list(replay["entities"]["queues"].values())[0]["maxsize"] == 2


def test_queues_level_names_a_queue_after_its_creation_line():
    with record(auto="queues") as rec:
        q = queue.Queue()
        q.put(1)
    created = [e for e in rec.events() if e.event_type == "queue.created"]
    assert created[0].metadata["name"].startswith("Queue (line ")


def test_queue_created_before_recording_is_not_observed():
    before = queue.Queue()
    with record(auto="queues") as rec:
        before.put(1)
        before.get()
    assert not types(rec.events(), "queue.")


def test_coverage_text_matches_the_level():
    none, threads, queues = (
        coverage_for(x) for x in ("none", "threads", "queues")
    )
    assert not any("every threading.Thread" in s for s in none["observed"])
    assert any("every threading.Thread" in s for s in threads["observed"])
    assert any(
        "Plain queue.Queue contents" in s for s in threads["not_observed"]
    )
    assert any("queue.Queue objects created" in s for s in queues["observed"])
    assert not any(
        "Plain queue.Queue contents" in s for s in queues["not_observed"]
    )


def test_recorded_metadata_states_the_level(tmp_path):
    out = tmp_path / "t.concurim"
    with record(out, auto="queues"):
        pass
    from concurim.recorder.serialization import load_trace

    meta = load_trace(out).metadata
    assert meta["config"]["auto"] == "queues"
    assert any("queue.Queue objects" in s for s in meta["coverage"]["observed"])
