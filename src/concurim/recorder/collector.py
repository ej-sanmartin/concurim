"""Thread-safe, bounded event collector.

Design rules (see docs/architecture.md):

* The collector lock is a raw ``threading.Lock`` held only for a few
  instructions and never while calling out to other code, so recording an
  event from inside an instrumented lock or queue mutex cannot deadlock.
* A per-thread reentrancy guard drops events emitted while already emitting.
* The buffer is bounded; overflow drops *new* events and is reported.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from typing import Any

from concurim.config import RecorderConfig
from concurim.recorder.events import Event, EventType, Source
from concurim.recorder.identities import IdentityRegistry

# Files whose frames are skipped when attributing an event to user code.
INTERNAL_FILES: set[str] = set()

_PRIMITIVES = (str, int, float, bool, type(None))


def mark_internal(filename: str) -> None:
    """Register a module file as instrumentation, not user code."""
    INTERNAL_FILES.add(filename)


mark_internal(__file__)


class Recorder:
    """Collects events for one recording session."""

    def __init__(self, config: RecorderConfig | None = None) -> None:
        self.config = config or RecorderConfig()
        self.ids = IdentityRegistry()
        self.process_id = os.getpid()
        self.started_wall_ns = time.time_ns()
        self._t0 = time.perf_counter_ns()
        self._lock = threading.Lock()
        self._reg_lock = threading.Lock()
        self._tls = threading.local()
        self._events: list[Event] = []
        self._sequence = 0
        self.dropped = 0
        self._cwd = self.config.source_root or os.getcwd()
        self._rel_cache: dict[str, str] = {}
        self.source_files: set[str] = set()
        # For the line sampler: OS thread ident -> actor ids.
        self.idents: dict[int, str] = {}
        self.running_task: dict[int, str | None] = {}
        self.samples_truncated = False
        self._remote: dict[str, str] = {}
        self._redact = [re.compile(p) for p in self.config.redact_patterns]

    @property
    def root(self) -> str:
        """Directory that user source files live under."""
        return self._cwd

    # -- identity ---------------------------------------------------------

    def new_object_id(self) -> str:
        """Allocate a logical id for a payload travelling through queues."""
        return self.ids.new_id("object")

    def resource_id(
        self, owner: Any, kind: str, name: str | None, metadata: dict[str, Any]
    ) -> str:
        """Return the owner's resource id, registering it on first use.

        Emits ``<kind>.created`` exactly once per owner and recorder.
        """
        reg = owner.__dict__.get("_cz_reg")
        if reg is not None and reg[0] is self:
            return reg[1]
        with self._reg_lock:
            reg = owner.__dict__.get("_cz_reg")
            if reg is not None and reg[0] is self:
                return reg[1]
            rid = self.ids.new_id(kind)
            owner._cz_reg = (self, rid)
        meta = dict(metadata)
        meta["name"] = name or rid
        self.emit(f"{kind}.created", resource_id=rid, metadata=meta)
        return rid

    # -- source and previews ---------------------------------------------

    def capture_source(self) -> Source | None:
        """Locate the nearest non-instrumentation frame, or ``None``."""
        if not self.config.capture_source_locations:
            return None
        frame = sys._getframe(1)
        while frame is not None and frame.f_code.co_filename in INTERNAL_FILES:
            frame = frame.f_back
        if frame is None:
            return None
        code = frame.f_code
        return Source(
            self.display_path(code.co_filename),
            frame.f_lineno,
            code.co_qualname,
        )

    def source_of_callable(self, func: Any) -> Source | None:
        """Source of a function definition (used for thread entry points)."""
        return self.source_of_code(getattr(func, "__code__", None))

    def source_of_code(self, code: Any) -> Source | None:
        """Source of a code object (functions, coroutines)."""
        if code is None or not self.config.capture_source_locations:
            return None
        return Source(
            self.display_path(code.co_filename),
            code.co_firstlineno,
            code.co_qualname,
        )

    def source_of_frame(self, frame: Any) -> Source | None:
        """Source of the line a (possibly suspended) frame is at."""
        if not self.config.capture_source_locations:
            return None
        code = frame.f_code
        return Source(
            self.display_path(code.co_filename),
            frame.f_lineno,
            code.co_qualname,
        )

    def display_path(self, filename: str) -> str:
        """Path shown in traces: relative to the start directory if inside."""
        cached = self._rel_cache.get(filename)
        if cached is not None:
            return cached
        self.source_files.add(filename)
        path = filename
        if os.path.isabs(filename):
            # realpath: on macOS ``/tmp`` is a symlink, so the path the
            # script was started with and ``co_filename`` can disagree.
            root = os.path.realpath(self._cwd)
            try:
                rel = os.path.relpath(os.path.realpath(filename), root)
            except ValueError:  # Windows: another drive has no relative path
                rel = ".."
            if not rel.startswith(".."):
                path = rel
        self._rel_cache[filename] = path
        return path

    def describe_payload(self, value: Any) -> dict[str, Any]:
        """Safe, bounded payload metadata.

        Never calls ``repr``/``str`` on arbitrary objects: only the exact
        built-in primitive types are previewed, and only when enabled.
        """
        info: dict[str, Any] = {"type": type(value).__name__}
        if self.config.preview and type(value) in _PRIMITIVES:
            text = str(value)
            for pattern in self._redact:
                text = pattern.sub("[redacted]", text)
            limit = self.config.preview_max_chars
            info["preview"] = text[:limit] + ("…" if len(text) > limit else "")
        return info

    # -- emission ---------------------------------------------------------

    def emit(
        self,
        event_type: str,
        *,
        resource_id: str | None = None,
        object_id: str | None = None,
        operation_id: str | None = None,
        caused_by: str | None = None,
        source: Source | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Record one event and return its id (``None`` if dropped)."""
        tls = self._tls
        if getattr(tls, "busy", False):
            return None
        tls.busy = True
        try:
            thread_id = getattr(tls, "thread_id", None)
            if thread_id is None:
                thread_id = self._register_current_thread()
            return self._append(
                event_type,
                thread_id,
                resource_id,
                object_id,
                operation_id,
                caused_by,
                source,
                metadata,
                getattr(tls, "task_id", None),
            )
        finally:
            tls.busy = False

    def _register_current_thread(self) -> str:
        thread = threading.current_thread()
        thread_id = self.ids.new_id("thread")
        self._tls.thread_id = thread_id
        self.idents[threading.get_ident()] = thread_id
        self._append(
            EventType.THREAD_REGISTERED,
            thread_id,
            None,
            None,
            None,
            None,
            None,
            {
                "name": thread.name,
                "ident": thread.ident or 0,
                "is_main": thread is threading.main_thread(),
                "daemon": thread.daemon,
            },
        )
        return thread_id

    def _append(
        self,
        event_type: str,
        thread_id: str | None,
        resource_id: str | None,
        object_id: str | None,
        operation_id: str | None,
        caused_by: str | None,
        source: Source | None,
        metadata: dict[str, Any] | None,
        task_id: str | None = None,
    ) -> str | None:
        now = time.perf_counter_ns() - self._t0
        with self._lock:
            if len(self._events) >= self.config.max_events:
                self.dropped += 1
                return None
            self._sequence += 1
            seq = self._sequence
            event_id = f"{self.process_id}-{seq}"
            self._events.append(
                Event(
                    event_id=event_id,
                    event_type=event_type,
                    timestamp_ns=now,
                    sequence=seq,
                    process_id=self.process_id,
                    thread_id=thread_id,
                    task_id=task_id,
                    resource_id=resource_id,
                    object_id=object_id,
                    operation_id=operation_id,
                    caused_by=caused_by,
                    source=source,
                    metadata=metadata or {},
                )
            )
        return event_id

    def current_actor(self) -> str:
        """Logical id of the calling thread (registered on first use)."""
        return (
            getattr(self._tls, "task_id", None)
            or getattr(self._tls, "thread_id", None)
            or self._register_current_thread()
        )

    def remote_actor(self, key: str, name: str, ident: int) -> str:
        """Logical actor for a worker in another process (registered once).

        Args:
            key: Stable key for the worker, such as its pid.
            name: Display name.
            ident: The worker's OS process id.
        """
        with self._reg_lock:
            actor = self._remote.get(key)
            if actor is not None:
                return actor
            actor = self._remote[key] = self.ids.new_id("process")
        self._append(
            EventType.THREAD_REGISTERED,
            actor,
            None,
            None,
            None,
            None,
            None,
            {
                "name": name,
                "ident": ident,
                "is_main": False,
                "daemon": True,
                "actor_kind": "process",
            },
        )
        return actor

    def emit_as(
        self,
        actor: str,
        event_type: str,
        *,
        resource_id: str | None = None,
        object_id: str | None = None,
        operation_id: str | None = None,
        source: Source | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Record an event on behalf of ``actor`` (a remote worker)."""
        return self._append(
            event_type,
            actor,
            resource_id,
            object_id,
            operation_id,
            None,
            source,
            metadata,
        )

    def set_task(self, task_id: str | None) -> None:
        """Attribute this thread's next events to an asyncio task."""
        self._tls.task_id = task_id
        self.running_task[threading.get_ident()] = task_id

    def new_operation_id(self) -> str:
        """Allocate an id linking the events of one logical operation."""
        return self.ids.new_id("operation")

    # -- results ----------------------------------------------------------

    def events(self) -> list[Event]:
        """A snapshot copy of the recorded events."""
        with self._lock:
            return list(self._events)

    def duration_ns(self) -> int:
        """Nanoseconds since the recorder was created (monotonic)."""
        return time.perf_counter_ns() - self._t0
