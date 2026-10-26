"""The trace the viewer is currently showing (replaceable at runtime)."""

from __future__ import annotations

import hashlib
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
        # The loaded trace and a hash of its replay (both for exporting).
        self.trace: Trace | None = None
        self.digest = ""
        self.event_count = 0
        self.generation = 0

    def load(self, trace: Trace, label: str) -> None:
        """Replace the current trace (the replay is built before swapping)."""
        replay = build_replay(trace)
        replay_json = json.dumps(replay, separators=(",", ":")).encode()
        with self._lock:
            self.replay_json = replay_json
            self.sources = dict(trace.sources)
            self.label = label
            self.trace = trace
            self.digest = hashlib.sha256(replay_json).hexdigest()
            self.event_count = len(replay["events"])
            self.generation += 1

    @property
    def has_trace(self) -> bool:
        """Whether a trace has been loaded."""
        return self.replay_json is not None
