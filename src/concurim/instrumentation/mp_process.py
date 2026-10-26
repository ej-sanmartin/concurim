"""Instrumented ``multiprocessing.Process``.

The parent records the start request; the child reports when its target
starts and how it ended (see ``mp_support``). Call ``join()`` so the
parent has received every report before the recording ends.
"""

from __future__ import annotations

import multiprocessing
from typing import Any

from concurim.instrumentation.mp_support import (
    Sink,
    child_call,
    child_init,
    describe_args,
)
from concurim.recorder.collector import mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.events import Source
from concurim.recorder.lifecycle import active_recorder
from concurim.recorder.sampler import wanted

mark_internal(__file__)

# Bound once: ``multiprocessing.Process`` may be replaced while patched.
_BaseProcess = multiprocessing.Process


class ProcessSink(Sink):
    """Turns one child's reports into thread lifecycle events."""

    source: Source | None = None

    def handle(self, report_: tuple[Any, ...]) -> None:
        """Record the child's start, sampled lines and end."""
        kind, _op, pid, pname, child_ns, error, where, _size = report_
        actor = self.actor(pid, pname)
        if kind == "line":
            self.line(actor, where)
        elif kind == "started":
            self.rec.emit_as(
                actor,
                E.THREAD_STARTED,
                source=self.source,
                metadata={"name": pname, "pid": pid, "child_ns": child_ns},
            )
        elif kind == "failed":
            self.rec.emit_as(
                actor, E.THREAD_FAILED, metadata={"error": error or "Exception"}
            )
        else:
            self.rec.emit_as(actor, E.THREAD_FINISHED)


class TracedProcess(_BaseProcess):
    """``multiprocessing.Process`` that records its start and end.

    Same constructor as ``multiprocessing.Process``. Outside a recording it
    behaves exactly like the standard class.
    """

    _cz_on = True

    def start(self) -> None:
        """Start the process, recording who asked and what it is given."""
        rec = active_recorder()
        if rec is None or not self._cz_on:
            super().start()
            return
        sink = ProcessSink(rec, multiprocessing.get_context())
        sink.source = rec.source_of_callable(self._target or type(self).run)  # ty: ignore[unresolved-attribute]
        self._cz_sink = sink
        self._cz_queue = sink.queue
        self._cz_sampling = (
            (rec.root, rec.config.sample_interval_ms / 1000)
            if wanted(rec.config)
            else None
        )
        rec.emit(
            E.THREAD_START_REQUESTED,
            source=rec.capture_source(),
            metadata={
                "child_name": self.name,
                "process": True,
                **describe_args(tuple(self._args), dict(self._kwargs)),  # ty: ignore[unresolved-attribute]
            },
        )
        sink.start()
        super().start()

    def run(self) -> None:
        """Runs in the child: report around the real ``run``."""
        queue = getattr(self, "_cz_queue", None)
        if queue is None:
            super().run()
            return
        child_init(queue, None, (), self._cz_sampling)
        child_call("run", super().run, (), {})

    def join(self, timeout: float | None = None) -> None:
        """``Process.join``; once the child is gone, flush its reports."""
        super().join(timeout)
        sink = getattr(self, "_cz_sink", None)
        if sink is not None and self.exitcode is not None:
            sink.close()

    def __getstate__(self) -> dict[str, Any]:
        """Leave parent-only state (threads) out of what a child unpickles."""
        state = self.__dict__.copy()
        state.pop("_cz_sink", None)
        return state
