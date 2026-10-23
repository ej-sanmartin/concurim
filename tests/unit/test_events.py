import pytest

from concurim.recorder.events import Event, Source, TraceFormatError


def make(**kw):
    base = dict(
        event_id="1-1",
        event_type="queue.put.completed",
        timestamp_ns=5,
        sequence=1,
        process_id=1,
    )
    base.update(kw)
    return Event(**base)


def test_roundtrip_and_omits_empty_fields():
    ev = make(
        thread_id="thread-1",
        source=Source("a.py", 3, "f"),
        metadata={"size_after": 2},
    )
    data = ev.to_dict()
    assert "task_id" not in data and "object_id" not in data
    assert Event.from_dict(data) == ev


@pytest.mark.parametrize(
    "patch",
    [
        {"schema_version": 2},
        {"event_id": 5},
        {"sequence": "1"},
        {"sequence": True},
        {"source": {"file": "a.py"}},
        {"metadata": {"x": [1]}},
        {"metadata": {"x": "y" * 600}},
        {"metadata": {f"k{i}": 1 for i in range(30)}},
    ],
)
def test_rejects_invalid(patch):
    data = make().to_dict() | patch
    with pytest.raises(TraceFormatError):
        Event.from_dict(data)


def test_rejects_non_object():
    with pytest.raises(TraceFormatError):
        Event.from_dict([1, 2])
