"""Starting and stopping recordings (the public ``record`` API)."""

from __future__ import annotations

import contextlib
import datetime
import sys
import threading
from pathlib import Path
from typing import Any

from concurim import __version__
from concurim.config import RecorderConfig
from concurim.recorder.collector import Recorder
from concurim.recorder.environment import coverage_for, environment_info
from concurim.recorder.flush import FlushGuard, still_blocked
from concurim.recorder.sampler import LineSampler, start_sampling
from concurim.recorder.serialization import MAX_SOURCE_BYTES, write_trace

_active: Recorder | None = None


def active_recorder() -> Recorder | None:
    """The recorder currently collecting events, if any."""
    return _active


def forget_recorder() -> None:
    """Make this process stop recording (used by forked worker processes,
    which inherit the parent's recorder but must not buffer events)."""
    global _active
    _active = None


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
        self.view_on_stop = False
        self.stop_snapshots = False
        self._save_lock = threading.Lock()
        self._auto: contextlib.AbstractContextManager[None] | None = None
        self._sampler: LineSampler | None = None
        self._guard: FlushGuard | None = None

    def __enter__(self) -> Recorder:
        global _active
        if _active is not None:
            raise RuntimeError("a Concurim recording is already active")
        _active = self.recorder
        self._sampler = start_sampling(self.recorder)
        if self.recorder.config.auto != "none":
            from concurim.instrumentation.auto import auto_instrument

            self._auto = auto_instrument(self.recorder.config.auto)
            self._auto.__enter__()
        if self.path is not None:
            self._guard = FlushGuard(self)
            self._guard.start()
        return self.recorder

    def __exit__(
        self, exc_type: type[BaseException] | None, *_: object
    ) -> None:
        global _active
        if self._guard is not None:
            self._guard.stop()
            self._guard = None
        if self._sampler is not None:
            self._sampler.stop()
            self.recorder.samples_truncated = self._sampler.exhausted
            self._sampler = None
        if self._auto is not None:
            self._auto.__exit__(None, None, None)
            self._auto = None
        _active = None
        if exc_type is not None and exc_type is not SystemExit:
            self.program.setdefault("exception", exc_type.__name__)
        self.finish(exc_type)

    def snapshot(self, kind: str, signal_name: str = "") -> bool:
        """Write the events collected so far.

        Args:
            kind: ``"running"`` or ``"interrupted"``.
            signal_name: ``SIGINT`` or ``SIGTERM`` when stopping for a signal.

        Returns:
            Whether a file was written.
        """
        with self._save_lock:
            if kind == "running" and (
                self.stop_snapshots
                or self.program.get("outcome") not in (None, "running")
                or not self.recorder.events()
            ):
                return False
            if kind == "interrupted":
                self.program["outcome"] = "interrupted"
                if signal_name:
                    self.program["signal"] = signal_name
                self.program["still_blocked"] = still_blocked()
            else:
                self.program["outcome"] = "running"
            return self._write()

    def finish(self, exc_type: type[BaseException] | None) -> None:
        """Write the final trace and record how the run ended."""
        self.stop_snapshots = True
        with self._save_lock:
            self._apply_outcome(exc_type)
            self._write()

    def save(self, path: str | Path) -> None:
        """Write the trace collected so far to ``path``."""
        with self._save_lock:
            self._write(Path(path))

    def _apply_outcome(self, exc_type: type[BaseException] | None) -> None:
        interrupted = (
            self.program.get("outcome") == "interrupted"
            or exc_type is KeyboardInterrupt
            or self.program.get("exception") == "KeyboardInterrupt"
        )
        if interrupted:
            self.program["outcome"] = "interrupted"
            self.program["still_blocked"] = still_blocked()
            return
        code = self.program.get("exit_code")
        failed = exc_type not in (None, SystemExit) or (
            isinstance(code, int) and code != 0
        )
        self.program["outcome"] = "failed" if failed else "finished"
        self.program["still_blocked"] = False

    def _write(self, path: Path | None = None) -> bool:
        """Write the zip. Caller holds ``_save_lock``."""
        dest = path if path is not None else self.path
        if dest is None:
            return False
        events = self.recorder.events()
        write_trace(
            dest,
            build_metadata(self.recorder, events, self.program),
            events,
            collect_sources(self.recorder),
        )
        return True


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
        "samples_truncated": recorder.samples_truncated,
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
