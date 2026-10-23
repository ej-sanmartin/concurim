"""Starting and stopping recordings (the public ``record`` API)."""

from __future__ import annotations

import contextlib
import datetime
import sys
from pathlib import Path
from typing import Any

from concurim import __version__
from concurim.config import RecorderConfig
from concurim.recorder.collector import Recorder
from concurim.recorder.environment import coverage_for, environment_info
from concurim.recorder.serialization import MAX_SOURCE_BYTES, write_trace

_active: Recorder | None = None


def active_recorder() -> Recorder | None:
    """The recorder currently collecting events, if any."""
    return _active


class record:  # noqa: N801 - used as a context manager, like ``open``
    """Record instrumented activity inside a ``with`` block.

    Args:
        path: Where to write the ``.concurim`` trace on exit (optional).
        config: A ``RecorderConfig``; keyword overrides build one.
        program: Extra metadata about the recorded program.

    Only one recording may be active at a time.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        config: RecorderConfig | None = None,
        program: dict[str, Any] | None = None,
        **config_kwargs: Any,
    ) -> None:
        if config is not None and config_kwargs:
            raise TypeError("pass either config or keyword options")
        self.path = Path(path) if path else None
        self.recorder = Recorder(config or RecorderConfig(**config_kwargs))
        self.program: dict[str, Any] = dict(program or {})
        self._auto: contextlib.AbstractContextManager[None] | None = None

    def __enter__(self) -> Recorder:
        global _active
        if _active is not None:
            raise RuntimeError("a Concurim recording is already active")
        _active = self.recorder
        if self.recorder.config.auto != "none":
            from concurim.instrumentation.auto import auto_instrument

            self._auto = auto_instrument(self.recorder.config.auto)
            self._auto.__enter__()
        return self.recorder

    def __exit__(
        self, exc_type: type[BaseException] | None, *_: object
    ) -> None:
        global _active
        if self._auto is not None:
            self._auto.__exit__(None, None, None)
            self._auto = None
        _active = None
        if exc_type is not None and exc_type is not SystemExit:
            self.program.setdefault("exception", exc_type.__name__)
        if self.path is not None:
            self.save(self.path)

    def save(self, path: str | Path) -> None:
        """Write the trace collected so far."""
        events = self.recorder.events()
        write_trace(
            path,
            build_metadata(self.recorder, events, self.program),
            events,
            collect_sources(self.recorder),
        )


def build_metadata(
    recorder: Recorder, events: list[Any], program: dict[str, Any]
) -> dict[str, Any]:
    """Assemble ``metadata.json`` contents for a finished recording."""
    return {
        "concurim_version": __version__,
        "created_at_utc": datetime.datetime.fromtimestamp(
            recorder.started_wall_ns / 1e9, datetime.UTC
        ).isoformat(),
        "duration_ns": recorder.duration_ns(),
        "event_count": len(events),
        "dropped_events": recorder.dropped,
        "truncated": recorder.dropped > 0,
        "config": recorder.config.public_dict(),
        "environment": environment_info(),
        "coverage": coverage_for(recorder.config.auto),
        "program": program,
        "argv0": Path(sys.argv[0]).name if sys.argv else None,
    }


def collect_sources(recorder: Recorder) -> dict[str, str]:
    """Read referenced user source files (only when opted in)."""
    if not recorder.config.include_source:
        return {}
    out: dict[str, str] = {}
    for filename in sorted(recorder.source_files):
        shown = recorder.display_path(filename)
        # Only project files: never absolute (outside cwd) or installed code.
        if Path(shown).is_absolute() or "site-packages" in shown:
            continue
        path = Path(filename)
        if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out[shown] = text
    return out
