"""Lineage, work spans, threads, privacy options and recorder lifecycle."""

import json
import queue  # noqa: F401
import threading
from importlib import resources
from pathlib import Path

import jsonschema
import pytest

import concurim
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace, load_trace
from concurim.replay.engine import build_replay
from conftest import run_threads, types


def replay_of(rec):
    return build_replay(Trace({}, rec.events()))


def test_lineage_and_work_spans(rec):
    a = concurim.TracedQueue(name="A")
    b = concurim.TracedQueue(name="B")
    a.put(3)
    item = a.get_with_id()
    with concurim.work("square", object_id=item.object_id):
        out = item.value**2
    b.put(out, derived_from=item.object_id)
    a.task_done(object_id=item.object_id)
    r = replay_of(rec)
    ents = r["entities"]["objects"]
    child = next(o for o in ents.values() if o["parent"] == item.object_id)
    assert child["id"] != item.object_id
    assert any(
        s["kind"] == "work" and s["outcome"] == "completed" for s in r["spans"]
    )
    assert r["warnings"] == []


def test_work_span_records_failure_and_propagates(rec):
    with pytest.raises(KeyError), concurim.work("boom"):
        raise KeyError("x")
    ev = rec.events()
    failed = next(e for e in ev if e.event_type == E.WORK_FAILED)
    assert failed.metadata["error"] == "KeyError"


def test_traced_thread_lifecycle_and_failure(rec, monkeypatch):
    seen = []
    monkeypatch.setattr(threading, "excepthook", lambda a: seen.append(a))

    def ok():
        pass

    def bad():
        raise ValueError("boom")

    run_threads(ok, bad)
    t = types(rec.events())
    assert t.count(E.THREAD_STARTED) == 2
    assert t.count(E.THREAD_FINISHED) == 1 and t.count(E.THREAD_FAILED) == 1
    assert len(seen) == 1 and seen[0].exc_type is ValueError
    started = [e for e in rec.events() if e.event_type == E.THREAD_STARTED]
    assert all(e.caused_by for e in started)  # explicit start edge


def test_preview_is_opt_in_bounded_and_never_calls_repr():
    class Hostile:
        def __repr__(self):
            raise AssertionError("repr must not be called")

        __str__ = __repr__

    with record() as r1:
        q = concurim.TracedQueue()
        q.put("secret-123")
    assert "preview" not in r1.events()[2].metadata  # default: off

    with record(
        preview=True, preview_max_chars=6, redact_patterns=(r"\d+",)
    ) as r2:
        q = concurim.TracedQueue()
        q.put("secret-123")
        q.put(Hostile())
    puts = [e for e in r2.events() if e.event_type == E.QUEUE_PUT_STARTED]
    assert puts[0].metadata["preview"] == "secret…"  # redact, then cut
    assert "123" not in puts[0].metadata["preview"]
    assert puts[1].metadata == {
        "block": True,
        "timeout": None,
        "maxsize": 0,
        "type": "Hostile",
    }


def test_buffer_overflow_is_reported_as_truncation(tmp_path):
    path = tmp_path / "t.concurim"
    with record(path, max_events=10):
        q = concurim.TracedQueue()
        for i in range(20):
            q.put(i)
    trace = load_trace(path)
    assert len(trace.events) == 10
    assert trace.metadata["truncated"] is True
    assert trace.metadata["dropped_events"] > 0
    assert "truncated" in build_replay(trace)["warnings"][0]


def test_only_one_recording_at_a_time():
    with record(), pytest.raises(RuntimeError), record():
        pass
    assert concurim.active_recorder() is None


def test_events_conform_to_published_json_schema(rec):
    q = concurim.TracedQueue(maxsize=1, name="Q")
    q.put(1)
    q.get()
    q.task_done()
    schema = json.loads(
        resources.files("concurim.schema")
        .joinpath("event.schema.json")
        .read_text()
    )
    for e in rec.events():
        jsonschema.validate(e.to_dict(), schema)


def test_source_locations_point_at_user_code(rec):
    q = concurim.TracedQueue(name="Q")
    q.put(1)  # <- source line expected here
    ev = next(e for e in rec.events() if e.event_type == E.QUEUE_PUT_STARTED)
    assert ev.source.file.endswith("test_recording_features.py")
    assert ev.source.function == "test_source_locations_point_at_user_code"
    lines = Path(__file__).read_text().splitlines()
    assert "q.put(1)" in lines[ev.source.line - 1]
