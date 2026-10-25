"""Approximate "what is each worker doing" by sampling thread stacks.

A daemon thread wakes every few milliseconds, looks at where each known
thread currently is, and reports the innermost line of *user* code when it
changed. This is a sample, not a trace: a line that runs for less than one
interval can be missed, and the position may be a few microseconds stale.
Sampling slows the program a little and never alters its behavior.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
from collections.abc import Callable, Hashable
from functools import lru_cache
from typing import Any

from concurim.config import RecorderConfig
from concurim.recorder.collector import INTERNAL_FILES, Recorder
from concurim.recorder.events import EventType as E
from concurim.recorder.events import Source

# Samples per sampler; a long loop cannot crowd out the real events.
MAX_SAMPLES = 100_000


def wanted(config: RecorderConfig) -> bool:
    """Whether recordings with ``config`` sample lines."""
    return (
        config.include_source
        and config.capture_source_locations
        and config.sample_interval_ms > 0
    )


@lru_cache(maxsize=4096)
def _under_root(filename: str, root: str) -> bool:
    """Is ``filename`` a project file (inside ``root``, not a package)?"""
    if filename.startswith("<"):
        return False
    if not os.path.isabs(filename):
        return True
    rel = os.path.relpath(os.path.realpath(filename), os.path.realpath(root))
    return not rel.startswith("..") and "site-packages" not in rel


class LineSampler:
    """Reports changes of each actor's current line of user code.

    Args:
        root: Directory whose files count as user code.
        interval_s: Seconds between samples.
        actor_of: Maps an OS thread ident to a hashable actor key, or
            ``None`` for threads that must not be sampled.
        emit: ``emit(actor, filename, line, qualname)``, called when an
            actor's line differs from its previous sample.
        limit: Stop after this many emitted samples (``exhausted``).
    """

    def __init__(
        self,
        root: str,
        interval_s: float,
        actor_of: Callable[[int], Hashable | None],
        emit: Callable[[Any, str, int, str], None],
        limit: int = MAX_SAMPLES,
    ) -> None:
        self._root = root
        self._interval = interval_s
        self._actor_of = actor_of
        self._emit = emit
        self._limit = limit
        self._count = 0
        self._last: dict[Hashable, tuple[Any, int]] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="concurim-sampler", daemon=True
        )
        self.exhausted = False

    def start(self) -> None:
        """Begin sampling in the background."""
        self._thread.start()

    def stop(self) -> None:
        """Stop sampling and wait briefly for the thread to end."""
        self._stop.set()
        if self._thread.is_alive() and self._thread is not (
            threading.current_thread()
        ):
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            # Recording must never alter or break the program being recorded.
            with contextlib.suppress(Exception):
                self.sample_once()

    def sample_once(self) -> None:
        """Take one sample of every sampled thread."""
        me = threading.get_ident()
        seen: dict[Hashable, tuple[Any, int]] = {}
        for ident, frame in sys._current_frames().items():
            actor = None if ident == me else self._actor_of(ident)
            if actor is None:
                continue
            while frame is not None and not self._is_user(frame.f_code):
                frame = frame.f_back
            if frame is None or frame.f_lineno is None:
                continue
            code, line = frame.f_code, frame.f_lineno
            seen[actor] = (code, line)
            if self._last.get(actor) != (code, line):
                self._emit(actor, code.co_filename, line, code.co_qualname)
                self._count += 1
                if self._count >= self._limit:
                    self.exhausted = True
                    self._stop.set()
                    break
        self._last = seen

    def _is_user(self, code: Any) -> bool:
        name = code.co_filename
        return name not in INTERNAL_FILES and _under_root(name, self._root)


def start_sampling(rec: Recorder) -> LineSampler | None:
    """Start sampling the threads and tasks of ``rec`` (if configured).

    Start it before automatic instrumentation, which would otherwise record
    the sampler's own thread as part of the program.
    """
    if not wanted(rec.config):
        return None

    def actor_of(ident: int) -> str | None:
        return rec.running_task.get(ident) or rec.idents.get(ident)

    def emit(actor: str, filename: str, line: int, name: str) -> None:
        rec.emit_as(
            actor,
            E.CODE_SAMPLED,
            source=Source(rec.display_path(filename), line, name),
        )

    sampler = LineSampler(
        rec.root, rec.config.sample_interval_ms / 1000, actor_of, emit
    )
    sampler.start()
    return sampler
