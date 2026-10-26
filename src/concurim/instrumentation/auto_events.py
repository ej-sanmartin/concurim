"""Automatic (patched-in) event and condition classes.

Used by ``auto_instrument``. The threading versions are traced only when
user code creates them: the standard library builds ``Event`` and
``Condition`` objects for its own use (``Thread``, ``queue.Queue``,
``Future``...), and those must stay plain.
"""

from __future__ import annotations

from typing import Any

from concurim.instrumentation.aio_events import (
    TracedAsyncCondition,
    TracedAsyncEvent,
)
from concurim.instrumentation.auto_support import creation_name, user_caller
from concurim.instrumentation.sync_events import (
    TracedCondition,
    TracedEvent,
)
from concurim.recorder.collector import mark_internal

mark_internal(__file__)


class AutoEvent(TracedEvent):
    """Traced only when created by user code."""

    def __init__(self) -> None:
        self._cz_on = user_caller(1)
        super().__init__(name=creation_name("Event") if self._cz_on else None)


class AutoCondition(TracedCondition):
    """Traced only when created by user code."""

    def __init__(self, lock: Any = None) -> None:
        self._cz_on = user_caller(1)
        super().__init__(
            lock, name=creation_name("Condition") if self._cz_on else None
        )


class AutoAsyncEvent(TracedAsyncEvent):
    """``TracedAsyncEvent`` named after the line that created it."""

    def __init__(self) -> None:
        super().__init__(name=creation_name("Event"))


class AutoAsyncCondition(TracedAsyncCondition):
    """``TracedAsyncCondition`` named after the line that created it."""

    def __init__(self, lock: Any = None) -> None:
        super().__init__(lock, name=creation_name("Condition"))
