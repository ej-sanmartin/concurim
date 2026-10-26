"""Worker reports as executor-style task events (pools of processes)."""

from __future__ import annotations

from typing import Any

from concurim.instrumentation.mp_support import Sink
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.events import Source

mark_internal(__file__)


class TaskSink(Sink):
    """Turns worker reports into ``executor.task.*`` events.

    ``pending`` maps an operation id to ``(resource id, object id, task
    name, source)`` for every task submitted and not yet finished.
    """

    def __init__(self, rec: Recorder, ctx: Any) -> None:
        super().__init__(rec, ctx)
        self.pending: dict[str, tuple[str, str, str, Source | None]] = {}

    def close(self) -> None:
        """Flush reports, then mark every worker process finished."""
        if self._closed:
            return
        super().close()
        for actor in self.actors:
            self.rec.emit_as(actor, E.THREAD_FINISHED)

    def handle(self, report_: tuple[Any, ...]) -> None:
        """Record the start, end or sampled line of one task."""
        kind, op, pid, pname, child_ns, error, where, size = report_
        known = self.pending.get(op)
        if known is None:
            return
        rid, oid, name, src = known
        actor = self.actor(pid, pname)
        if kind == "line":
            self.line(actor, where)
            return
        meta: dict[str, Any] = {
            "name": name,
            "worker_pid": pid,
            "child_ns": child_ns,
        }
        if kind == "started":
            etype = E.EXECUTOR_TASK_STARTED
        else:
            del self.pending[op]
            src = None
            if kind == "failed":
                meta["error"] = error or "Exception"
                etype = E.EXECUTOR_TASK_FAILED
            else:
                etype = E.EXECUTOR_TASK_FINISHED
                if size is not None:
                    meta["result_bytes"] = size
        self.rec.emit_as(
            actor,
            etype,
            resource_id=rid,
            object_id=oid,
            operation_id=op,
            source=src,
            metadata=meta,
        )
