"""Thread lifecycle instrumentation.

``observe_thread`` is the single implementation. It is used by
``TracedThread`` (explicit) and by the reversible ``threading.Thread.start``
patch in ``instrumentation/auto.py`` (automatic).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from concurim.recorder.collector import mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)
mark_internal(threading.__file__)

# Threads whose entry point is defined in one of these files are plumbing
# (an executor's manager thread, a queue's feeder), not part of the workload.
PLUMBING_FILES: set[str] = set()


def observe_thread(thread: threading.Thread) -> None:
    """Record ``thread``'s start request, start, finish or failure.

    Call just before ``thread.start()``. It wraps this one instance's
    ``run`` (so subclasses that override ``run`` are covered) and does
    nothing if no recording is active or the thread was already observed.
    The thread's exception still propagates to ``threading.excepthook``.

    Args:
        thread: A thread that has not been started yet.
    """
    rec = active_recorder()
    if rec is None or getattr(thread, "_cz_observed", False):
        return
    target = getattr(thread, "_target", None) or type(thread).run
    code = getattr(target, "__code__", None)
    if code is not None and code.co_filename in PLUMBING_FILES:
        return
    thread._cz_observed = True  # ty: ignore[unresolved-attribute]
    start_event = rec.emit(
        E.THREAD_START_REQUESTED,
        source=rec.capture_source(),
        metadata={"child_name": thread.name},
    )
    inner = thread.run

    def run() -> None:
        rec.emit(
            E.THREAD_STARTED,
            caused_by=start_event,
            source=rec.source_of_callable(target),
            metadata={"name": thread.name},
        )
        try:
            inner()
        except BaseException as error:
            rec.emit(E.THREAD_FAILED, metadata={"error": type(error).__name__})
            raise
        rec.emit(E.THREAD_FINISHED)

    thread.run = run  # ty: ignore[invalid-assignment]


class TracedThread(threading.Thread):
    """A ``threading.Thread`` that records its lifecycle.

    Same constructor as ``threading.Thread``. Records ``start()`` (with the
    starter's source location), thread start, normal finish, or the
    exception type that ended it.
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

    def start(self) -> None:
        """Start the thread, recording who requested it."""
        observe_thread(self)
        super().start()
