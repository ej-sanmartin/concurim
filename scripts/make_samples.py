"""Regenerate the gallery's sample traces.

Each sample is a REAL recording: the program next to it is run through
``concurim record`` exactly as a user would. Timing varies between runs, so
regenerating changes the binary files; commit them only when intended.

Usage: uv run python scripts/make_samples.py
"""

import subprocess
import sys

from concurim.recorder.serialization import load_trace
from concurim.replay.engine import build_replay
from concurim.samples import SAMPLES_DIR, load_manifest


def record(entry: dict) -> None:
    """Record one manifest entry and sanity-check the result."""
    out = SAMPLES_DIR / entry["trace"]
    cmd = [
        sys.executable,
        "-m",
        "concurim",
        "record",
        "--include-source",
        "--auto",
        entry["auto"],
        "-o",
        str(out),
        entry["source"],
    ]
    subprocess.run(  # noqa: S603 - fixed, trusted command
        cmd, cwd=SAMPLES_DIR, check=True, capture_output=True
    )
    trace = load_trace(out)
    replay = build_replay(trace)
    assert not replay["warnings"], (entry["id"], replay["warnings"])
    blob = str(trace.metadata)
    assert str(SAMPLES_DIR) not in blob, "absolute path leaked into a sample"
    count = len(trace.events)
    print(f"{entry['id']:18} {count:4} events  {out.stat().st_size} bytes")


def main() -> None:
    for entry in load_manifest()["samples"]:
        record(entry)


if __name__ == "__main__":
    main()
