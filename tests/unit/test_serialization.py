import json
import zipfile

import pytest

from concurim.recorder.events import Event, TraceFormatError
from concurim.recorder.serialization import load_trace, write_trace


def ev(seq, **kw):
    return Event(
        event_id=f"1-{seq}",
        event_type="queue.created",
        timestamp_ns=seq,
        sequence=seq,
        process_id=1,
        **kw,
    )


def test_write_load_roundtrip(tmp_path):
    path = tmp_path / "t.concurim"
    write_trace(
        path,
        {"program": {"script": "x.py"}},
        [ev(1), ev(2)],
        {"x.py": "print(1)\n"},
    )
    trace = load_trace(path)
    assert [e.sequence for e in trace.events] == [1, 2]
    assert trace.sources == {"x.py": "print(1)\n"}
    assert trace.metadata["format"] == "concurim-trace"


def test_not_a_zip(tmp_path):
    bad = tmp_path / "bad.concurim"
    bad.write_text("nope")
    with pytest.raises(TraceFormatError):
        load_trace(bad)


def _rewrite(path, **members):
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in members.items():
            zf.writestr(name.replace("__", "/"), text)


def test_missing_members(tmp_path):
    path = tmp_path / "t.concurim"
    _rewrite(path, **{"metadata.json": "{}"})
    with pytest.raises(TraceFormatError, match="missing"):
        load_trace(path)


def test_wrong_format_version(tmp_path):
    path = tmp_path / "t.concurim"
    meta = json.dumps({"format": "concurim-trace", "format_version": 99})
    _rewrite(path, **{"metadata.json": meta, "events.jsonl": ""})
    with pytest.raises(TraceFormatError, match="format_version"):
        load_trace(path)


def test_rejects_decreasing_sequence(tmp_path):
    path = tmp_path / "t.concurim"
    write_trace(path, {}, [ev(2), ev(1)], {})
    with pytest.raises(TraceFormatError, match="sequence"):
        load_trace(path)


def test_rejects_source_entry_outside_sources_dir(tmp_path):
    path = tmp_path / "t.concurim"
    meta = {
        "format": "concurim-trace",
        "format_version": 1,
        "sources": {"evil": "events.jsonl"},
    }
    _rewrite(path, **{"metadata.json": json.dumps(meta), "events.jsonl": ""})
    with pytest.raises(TraceFormatError, match="source"):
        load_trace(path)


def test_garbage_event_line(tmp_path):
    path = tmp_path / "t.concurim"
    meta = {"format": "concurim-trace", "format_version": 1}
    _rewrite(
        path,
        **{"metadata.json": json.dumps(meta), "events.jsonl": "{not json}\n"},
    )
    with pytest.raises(TraceFormatError, match="events.jsonl:1"):
        load_trace(path)
