"""Instrumented ``threading.Thread``."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)
mark_internal(threading.__file__)


class TracedThread(threading.Thread):
    """A ``threading.Thread`` that records its lifecycle.

    Records ``start()`` (with the starter's source location), thread start,
    normal finish, or the exception type that ended it. Subclasses that
    override ``run()`` without calling ``super().run()`` are not recorded.
    The exception still propagates to ``threading.excepthook`` as usual.
    """

    def __init__(
        self,
        group: None = None,
        target: Callable[..., object] | None = None,
        name: str | None = None,
        args: Iterable[Any] = (),
        kwargs: Mapping[str, Any] | None = None,
        *,
        daemon: bool | None = None,
    ) -> None:
        super().__init__(group, target, name, args, kwargs, daemon=daemon)
        self._cz_target = target
        self._cz_rec: Recorder | None = None
        self._cz_start_event: str | None = None

    def start(self) -> None:
        """Start the thread, recording who requested it."""
        rec = active_recorder()
        self._cz_rec = rec
        if rec is not None:
            self._cz_start_event = rec.emit(
                E.THREAD_START_REQUESTED,
                source=rec.capture_source(),
                metadata={"child_name": self.name},
            )
        super().start()

    def run(self) -> None:
        """Run the thread body, recording started/finished/failed."""
        rec = self._cz_rec
        if rec is None:
            return super().run()
        rec.emit(
            E.THREAD_STARTED,
            caused_by=self._cz_start_event,
            source=rec.source_of_callable(self._cz_target),
            metadata={"name": self.name},
        )
        try:
            super().run()
        except BaseException as error:
            rec.emit(E.THREAD_FAILED, metadata={"error": type(error).__name__})
            raise
        rec.emit(E.THREAD_FINISHED)
        return None
