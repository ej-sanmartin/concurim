"""A program that never returns still leaves a viewable trace."""

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from concurim.recorder.serialization import load_trace
from concurim.replay.engine import build_replay

DEADLOCK = textwrap.dedent(
    """
    import threading
    import time

    lock_a = threading.Lock()
    lock_b = threading.Lock()
    held = [threading.Event(), threading.Event()]

    def take(first, second, mine, other):
        first.acquire()
        mine.set()
        other.wait()
        second.acquire()

    threads = [
        threading.Thread(
            target=take, args=(lock_a, lock_b, held[0], held[1]),
            name="A-then-B",
        ),
        threading.Thread(
            target=take, args=(lock_b, lock_a, held[1], held[0]),
            name="B-then-A",
        ),
    ]
    for thread in threads:
        thread.start()
    if not all(flag.wait(2) for flag in held):
        raise SystemExit("not armed")
    time.sleep(0.3)
    print("READY", flush=True)
    for thread in threads:
        thread.join()
    """
)


def test_a_deadlock_is_saved_when_the_process_is_signalled(tmp_path: Path):
    script = tmp_path / "dead.py"
    script.write_text(DEADLOCK)
    out = tmp_path / "dead.concurim"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "concurim",
            "record",
            "--auto",
            "sync",
            "-o",
            str(out),
            str(script),
        ],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdout is not None
    lines: list[str] = []
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line)
        if "READY" in line:
            break
    assert any("READY" in line for line in lines), "".join(lines)
    proc.send_signal(signal.SIGTERM)
    output, _ = proc.communicate(timeout=15)
    assert out.is_file(), output
    trace = load_trace(out)
    program = trace.metadata["program"]
    assert program["outcome"] == "interrupted"
    assert program["still_blocked"] is True
    replay = build_replay(trace)
    assert replay["wait_for"]["cycles"]
    assert set(replay["wait_for"]["cycles"][0]) == {"A-then-B", "B-then-A"}
    assert any("still true" in warning for warning in replay["warnings"])


def test_a_running_program_is_snapshotted_before_it_exits(tmp_path: Path):
    script = tmp_path / "slow.py"
    script.write_text(
        "import threading, time\n"
        "threading.Thread(target=lambda: None).start()\n"
        "time.sleep(3)\n"
    )
    out = tmp_path / "slow.concurim"
    env = dict(os.environ, CONCURIM_FLUSH_S="0.2")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "concurim",
            "record",
            "--auto",
            "threads",
            "-o",
            str(out),
            str(script),
        ],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not out.is_file():
        time.sleep(0.05)
    assert out.is_file()
    program = load_trace(out).metadata["program"]
    assert program["outcome"] in ("running", "finished")
    proc.wait(timeout=10)
