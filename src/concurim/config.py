"""Recorder configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Automatic instrumentation levels; each includes the ones before it.
LEVELS = ("none", "threads", "queues", "sync", "asyncio")


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
        auto: Automatic instrumentation level while recording, each level
            including the previous: ``"none"`` (only Concurim-managed
            objects), ``"threads"`` (every ``threading.Thread``),
            ``"queues"`` (``queue.Queue`` objects created during the run),
            ``"sync"`` (locks, semaphores and ``ThreadPoolExecutor``
            created by your code) or ``"asyncio"`` (tasks and asyncio
            queues, locks and semaphores).
        source_root: Directory that recorded paths are shown relative to,
            and the only place source files may be embedded from. Defaults
            to the current directory when recording starts.
        sample_interval_ms: How often (milliseconds) a background thread
            samples which line each worker is running, so the code view can
            follow the work between instrumented calls. Only used with
            ``include_source``; ``0`` turns sampling off. Sampling is
            approximate and slightly slows the program.
    """

    max_events: int = 1_000_000
    include_source: bool = False
    capture_source_locations: bool = True
    preview: bool = False
    preview_max_chars: int = 48
    redact_patterns: tuple[str, ...] = ()
    source_root: str | None = None
    auto: str = "none"
    sample_interval_ms: float = 5.0

    def __post_init__(self) -> None:
        if self.auto not in LEVELS:
            raise ValueError(f"unknown auto level {self.auto!r}")
        if self.max_events < 1:
            raise ValueError("max_events must be positive")
        if not 0 <= self.preview_max_chars <= 256:
            raise ValueError("preview_max_chars must be in [0, 256]")
        if not 0 <= self.sample_interval_ms <= 10_000:
            raise ValueError("sample_interval_ms must be in [0, 10000]")
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
            "sample_interval_ms": self.sample_interval_ms,
        }
