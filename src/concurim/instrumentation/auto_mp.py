"""Automatic variants of ``multiprocessing.Process`` and ``Pool``.

Traced only when user code creates them, so processes and pools the
standard library or a package makes for itself stay plain.
"""

from __future__ import annotations

from typing import Any

from concurim.instrumentation.auto_support import creation_name, user_caller
from concurim.instrumentation.mp_pool import TracedPool
from concurim.instrumentation.mp_process import TracedProcess
from concurim.recorder.collector import mark_internal

mark_internal(__file__)


class AutoProcess(TracedProcess):
    """``TracedProcess`` that only records when user code created it."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._cz_on = user_caller(1)


class AutoPool(TracedPool):
    """``TracedPool`` named after the line that created it."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._cz_on = user_caller(1)
        kwargs["name"] = creation_name("Pool")
        super().__init__(*args, **kwargs)
