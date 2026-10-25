"""Code view data: function ranges and sampled lines."""

import multiprocessing
from pathlib import Path

import pool_tasks
import pytest

import concurim
from concurim.config import RecorderConfig
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import record
from concurim.recorder.serialization import Trace, load_trace
from concurim.replay.code_view import function_ranges
from concurim.replay.engine import build_replay
from concurim.runner import run_recorded

SPAWN = multiprocessing.get_context("spawn")

SCRIPT = """\
import threading
import time


def busy():
    total = 0
    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        total += 1
    return total


worker = threading.Thread(target=busy)
worker.start()
worker.join()
"""


def sampled(events, function):
    return [
        e
        for e in events
        if e.event_type == E.CODE_SAMPLED
        and e.source is not None
        and e.source.function == function
    ]


def test_function_ranges_cover_decorators_nesting_and_async():
    text = (
        "@decorator\n"  # 1
        "def outer():\n"  # 2
        "    def inner():\n"  # 3
        "        pass\n"  # 4
        "    return inner\n"  # 5
        "\n"
        "async def coro():\n"  # 7
        "    await x\n"  # 8
    )
    assert function_ranges({"a.py": text}) == {"a.py": [[1, 5], [3, 4], [7, 8]]}


def test_function_ranges_skip_files_that_do_not_parse():
    assert function_ranges({"bad.py": "def (:\n", "ok.py": "pass\n"}) == {}


def test_a_busy_thread_is_sampled_inside_its_function(tmp_path):
    script = tmp_path / "app.py"
    script.write_text(SCRIPT)
    out = tmp_path / "run.concurim"
    config = RecorderConfig(
        include_source=True,
        auto="threads",
        source_root=str(tmp_path.resolve()),
    )
    run_recorded(script, [], out, config)
    trace = load_trace(out)
    hits = sampled(trace.events, "busy")
    assert hits
    assert {e.source.file for e in hits} == {"app.py"}
    assert all(6 <= e.source.line <= 10 for e in hits)
    assert {e.thread_id for e in hits} != {None}

    replay = build_replay(trace)
    assert all(e["event_type"] != E.CODE_SAMPLED for e in replay["events"])
    assert replay["summary"]["event_count"] == len(replay["frames"])
    assert replay["code_ranges"]["app.py"] == [[5, 10]]
    assert {s["function"] for s in replay["line_samples"]} >= {"busy"}
    last = len(replay["events"]) - 1
    assert all(0 <= s["at"] <= last for s in replay["line_samples"])


@pytest.mark.parametrize(
    "options",
    [
        {"include_source": False},
        {"include_source": True, "sample_interval_ms": 0},
        {"include_source": True, "capture_source_locations": False},
    ],
)
def test_sampling_is_off_unless_asked_for(tmp_path, options):
    script = tmp_path / "app.py"
    script.write_text(SCRIPT)
    out = tmp_path / "run.concurim"
    config = RecorderConfig(
        auto="threads", source_root=str(tmp_path.resolve()), **options
    )
    run_recorded(script, [], out, config)
    assert sampled(load_trace(out).events, "busy") == []


def test_the_sampler_thread_is_not_recorded_as_part_of_the_program(tmp_path):
    script = tmp_path / "app.py"
    script.write_text(SCRIPT)
    out = tmp_path / "run.concurim"
    config = RecorderConfig(
        include_source=True,
        auto="threads",
        source_root=str(tmp_path.resolve()),
    )
    run_recorded(script, [], out, config)
    names = [
        e.metadata.get("name")
        for e in load_trace(out).events
        if e.event_type == E.THREAD_REGISTERED
    ]
    assert "concurim-sampler" not in names


def test_sample_limit_is_reported_in_the_replay():
    meta = {"program": {}, "samples_truncated": True}
    assert any(
        "sampling" in w for w in build_replay(Trace(meta, [], {}))["warnings"]
    )


def test_process_pool_workers_are_sampled_inside_their_task():
    # Longer than the task, so the hit is the worker recording the
    # function it entered.
    config = RecorderConfig(
        include_source=True,
        source_root=str(Path(__file__).parent),
        sample_interval_ms=10_000,
    )
    with (
        record(config=config) as rec,
        concurim.TracedProcessPoolExecutor(
            1, mp_context=SPAWN, name="Pool"
        ) as pool,
    ):
        pool.submit(pool_tasks.slow, 0.3).result()
    events = rec.events()
    hits = sampled(events, "slow")
    assert hits
    assert {e.source.file for e in hits} == {"pool_tasks.py"}
    registered = {
        e.thread_id
        for e in events
        if e.event_type == E.THREAD_REGISTERED
        and e.metadata.get("actor_kind") == "process"
    }
    assert {e.thread_id for e in hits} <= registered
    started = next(e for e in events if e.event_type == E.EXECUTOR_TASK_STARTED)
    assert all(e.sequence > started.sequence for e in hits)
