"""Regenerate frontend test fixtures.

``pipeline.replay.json`` is a REAL capture: the bundled threaded example is
recorded with Concurim and converted to a replay document. Its timing varies
per run, so frontend tests assert invariants, not exact interleavings.

Usage: uv run python scripts/make_fixtures.py
"""

import json
import tempfile
from pathlib import Path

from concurim.config import RecorderConfig
from concurim.recorder.serialization import load_trace
from concurim.replay.engine import build_replay
from concurim.runner import run_recorded

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "tests" / "fixtures"


def main() -> None:
    script = ROOT / "src" / "concurim" / "samples" / "threaded_pipeline.py"
    with tempfile.TemporaryDirectory() as tmp:
        trace_path = Path(tmp) / "pipeline.concurim"
        config = RecorderConfig(
            include_source=True, source_root=str(script.parent)
        )
        code, _ = run_recorded(script, [], trace_path, config)
        assert code == 0
        replay = build_replay(load_trace(trace_path))
    replay["metadata"]["fixture"] = (
        "real capture of samples/threaded_pipeline.py"
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pipeline.replay.json").write_text(json.dumps(replay))
    print(f"wrote {OUT / 'pipeline.replay.json'}")


if __name__ == "__main__":
    main()
