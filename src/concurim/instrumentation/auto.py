"""Reversible automatic instrumentation (no code changes needed).

Levels, from least to most invasive:

``"threads"``
    Wraps ``threading.Thread.start`` so every thread started during the
    recording reports its lifecycle. Nothing else is touched.
``"queues"``
    Additionally replaces ``queue.Queue`` with a traced subclass, so
    queues created *during* the recording are observed. Queues created
    earlier, ``LifoQueue``, ``PriorityQueue`` and ``SimpleQueue`` are not.

Both patches are restored on exit, even if the program fails. Code that
inspects ``Queue.queue`` directly sees internal envelopes while patched.
"""

from __future__ import annotations

import contextlib
import queue
import threading
from collections.abc import Callable, Generator
from typing import Any

from concurim.instrumentation.queues import TracedQueue
from concurim.instrumentation.threads import observe_thread
from concurim.recorder.collector import mark_internal
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)

LEVELS = ("none", "threads", "queues")


class AutoQueue(TracedQueue):
    """``TracedQueue`` named after the line that created it."""

    def __init__(self, maxsize: int = 0) -> None:
        rec = active_recorder()
        source = rec.capture_source() if rec else None
        name = f"Queue (line {source.line})" if source else None
        super().__init__(maxsize, name=name)


def _wrapped_start(original: Callable[..., Any]) -> Callable[..., Any]:
    def start(self: threading.Thread) -> None:
        observe_thread(self)
        original(self)

    return start


@contextlib.contextmanager
def auto_instrument(level: str) -> Generator[None]:
    """Apply the patches for ``level`` for the duration of the block.

    Args:
        level: One of ``LEVELS``.

    Raises:
        ValueError: For an unknown level.
    """
    if level not in LEVELS:
        raise ValueError(f"unknown auto-instrumentation level {level!r}")
    original_start = threading.Thread.start
    original_queue = queue.Queue
    try:
        if level != "none":
            threading.Thread.start = _wrapped_start(original_start)  # ty: ignore[invalid-assignment]
        if level == "queues":
            queue.Queue = AutoQueue  # ty: ignore[invalid-assignment]
        yield
    finally:
        threading.Thread.start = original_start
        queue.Queue = original_queue
