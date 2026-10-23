"""The trace the viewer is currently showing (replaceable at runtime)."""

from __future__ import annotations

import json
import threading

from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay


class Session:
    """Holds the prepared replay document and the sources it may serve."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.replay_json: bytes | None = None
        self.sources: dict[str, str] = {}
        self.label: str | None = None
        self.generation = 0

    def load(self, trace: Trace, label: str) -> None:
        """Replace the current trace (the replay is built before swapping)."""
        replay_json = json.dumps(
            build_replay(trace), separators=(",", ":")
        ).encode()
        with self._lock:
            self.replay_json = replay_json
            self.sources = dict(trace.sources)
            self.label = label
            self.generation += 1

    @property
    def has_trace(self) -> bool:
        """Whether a trace has been loaded."""
        return self.replay_json is not None
