"""Explicit work spans: make "what a worker is doing" observable."""

from __future__ import annotations

from types import TracebackType

from concurim.recorder.collector import mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)


class work:  # noqa: N801 - used like a context manager factory
    """Mark a block of code as work done by the current thread.

    ``with work("resize", object_id=item.object_id): ...`` records when the
    thread started and finished the block, and which object it was working
    on. This is the only way Concurim *observes* processing; without it,
    processing between queue operations is inferred, never observed.
    """

    def __init__(self, name: str, object_id: str | None = None) -> None:
        self.name = name[:128]
        self.object_id = object_id
        self._rec = None
        self._op: str | None = None

    def __enter__(self) -> work:
        rec = active_recorder()
        if rec is not None:
            self._rec = rec
            self._op = rec.new_operation_id()
            rec.emit(
                E.WORK_STARTED,
                object_id=self.object_id,
                operation_id=self._op,
                source=rec.capture_source(),
                metadata={"name": self.name},
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        rec = self._rec
        if rec is None:
            return
        if exc_type is None:
            rec.emit(
                E.WORK_FINISHED,
                object_id=self.object_id,
                operation_id=self._op,
                metadata={"name": self.name},
            )
        else:
            rec.emit(
                E.WORK_FAILED,
                object_id=self.object_id,
                operation_id=self._op,
                metadata={"name": self.name, "error": exc_type.__name__},
            )
