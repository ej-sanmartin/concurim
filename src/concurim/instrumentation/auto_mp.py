"""Automatic variants of the ``multiprocessing`` classes.

Traced only when user code creates them, so processes, pools, locks and
values the standard library or a package makes for itself stay plain (a
``Pool``'s internal locks, say). Locks and values are made through a
context (``multiprocessing.Lock()`` is one), so that is what is patched:
the classes themselves must stay the real ones, or pickling a plain lock
fails.
"""

from __future__ import annotations

import multiprocessing
import multiprocessing.context
import types
from collections.abc import Callable
from typing import Any

from concurim.instrumentation.auto_support import creation_name, user_caller
from concurim.instrumentation.mp_pool import TracedPool
from concurim.instrumentation.mp_process import TracedProcess
from concurim.instrumentation.mp_signals import TracedMPBarrier, TracedMPEvent
from concurim.instrumentation.mp_sync import (
    TracedMPBoundedSemaphore,
    TracedMPLock,
    TracedMPRLock,
    TracedMPSemaphore,
)
from concurim.instrumentation.mp_value import traced_value
from concurim.recorder.collector import mark_internal

mark_internal(__file__)

_Context = multiprocessing.context.BaseContext
_TRACED_SYNC = {
    "Lock": TracedMPLock,
    "RLock": TracedMPRLock,
    "Semaphore": TracedMPSemaphore,
    "BoundedSemaphore": TracedMPBoundedSemaphore,
    "Event": TracedMPEvent,
    "Barrier": TracedMPBarrier,
}


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


def _sync_method(label: str) -> Callable[..., Any]:
    """``BaseContext.<label>`` that traces what user code creates."""
    real = getattr(_Context, label)
    traced = _TRACED_SYNC[label]

    def method(self: Any, *args: Any, **kwargs: Any) -> Any:
        if not user_caller(1):
            return real(self, *args, **kwargs)
        return traced(
            *args, ctx=self.get_context(), name=creation_name(label), **kwargs
        )

    method.__name__ = label
    return method


def _value_method() -> Callable[..., Any]:
    """``BaseContext.Value`` that traces the values user code creates."""
    real = _Context.Value

    def Value(self: Any, typecode_or_type: Any, *args: Any, lock: Any = True):
        if not user_caller(1):
            return real(self, typecode_or_type, *args, lock=lock)
        return traced_value(
            typecode_or_type,
            *args,
            lock=lock,
            name=creation_name("Value"),
            ctx=self.get_context(),
        )

    return Value


def mp_primitive_patches() -> list[tuple[Any, str, Any]]:
    """``(owner, attribute, replacement)`` for the shared primitives.

    Locks, semaphores, events, barriers and ``Value``.

    Each is patched on ``BaseContext`` (for ``get_context(...)``) and on the
    ``multiprocessing`` module, whose ``Lock`` and friends are methods of the
    default context bound at import.
    """
    default = multiprocessing.context._default_context
    methods = {n: _sync_method(n) for n in _TRACED_SYNC}
    methods["Value"] = _value_method()
    out: list[tuple[Any, str, Any]] = []
    for name, method in methods.items():
        out.append((_Context, name, method))
        out.append((multiprocessing, name, types.MethodType(method, default)))
    return out
