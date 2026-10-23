"""Recorder configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecorderConfig:
    """Options controlling what is recorded.

    Attributes:
        max_events: Hard cap on buffered events. When reached, *new* events
            are dropped (the earliest events keep the trace coherent) and the
            trace is marked truncated.
        include_source: Embed the text of referenced source files in the
            trace. Off by default because sources may be sensitive.
        capture_source_locations: Record file/line/function per event. Turn
            off for the lightest recording mode.
        preview: Record a bounded preview of primitive payloads. Off by
            default because payloads may be sensitive.
        preview_max_chars: Maximum characters kept in a preview.
        redact_patterns: Regexes replaced by ``[redacted]`` in previews.
        auto: Automatic instrumentation level while recording: ``"none"``
            (only Concurim-managed objects), ``"threads"`` (every
            ``threading.Thread``) or ``"queues"`` (threads plus
            ``queue.Queue`` objects created during the run).
        source_root: Directory that recorded paths are shown relative to,
            and the only place source files may be embedded from. Defaults
            to the current directory when recording starts.
    """

    max_events: int = 1_000_000
    include_source: bool = False
    capture_source_locations: bool = True
    preview: bool = False
    preview_max_chars: int = 48
    redact_patterns: tuple[str, ...] = ()
    source_root: str | None = None
    auto: str = "none"

    def __post_init__(self) -> None:
        if self.auto not in ("none", "threads", "queues"):
            raise ValueError(f"unknown auto level {self.auto!r}")
        if self.max_events < 1:
            raise ValueError("max_events must be positive")
        if not 0 <= self.preview_max_chars <= 256:
            raise ValueError("preview_max_chars must be in [0, 256]")
        for pattern in self.redact_patterns:
            re.compile(pattern)

    @classmethod
    def light(cls) -> RecorderConfig:
        """Lightweight mode: no source locations, no previews."""
        return cls(capture_source_locations=False)

    def public_dict(self) -> dict[str, object]:
        """Config values safe to store in trace metadata."""
        return {
            "max_events": self.max_events,
            "include_source": self.include_source,
            "capture_source_locations": self.capture_source_locations,
            "preview": self.preview,
            "auto": self.auto,
        }
