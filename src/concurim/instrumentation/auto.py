"""Reversible automatic instrumentation (no code changes needed).

Levels, from least to most invasive; each includes the ones before it:

``"threads"``
    Wraps ``threading.Thread.start`` so every thread started during the
    recording reports its lifecycle. Nothing else is touched.
``"queues"``
    Replaces ``queue.Queue`` with a traced subclass, so queues created
    *during* the recording are observed. Queues created earlier,
    ``LifoQueue``, ``PriorityQueue`` and ``SimpleQueue`` are not.
``"sync"``
    Replaces ``threading.Lock/RLock/Semaphore/BoundedSemaphore/Event/
    Condition/Barrier``, ``ThreadPoolExecutor``, ``ProcessPoolExecutor``,
    ``multiprocessing.Process`` and ``multiprocessing.Pool`` (task start and
    end in each worker process). Only objects created directly by
    *your* code are traced: ones created inside the standard library or
    installed packages (for example an ``Event``'s internal lock) are plain.
``"asyncio"``
    Records asyncio task creation and every task step of the event loop, and
    replaces ``asyncio.Queue/Lock/Semaphore/BoundedSemaphore/Event/
    Condition/Barrier/TaskGroup``.

All patches are restored on exit, even if the program fails. Code that
inspects ``Queue.queue`` sees the original items; ``isinstance(x,
threading.Lock)`` is False for patched locks while recording.
"""

from __future__ import annotations

import _thread
import asyncio
import asyncio.base_events
import asyncio.events
import concurrent.futures
import concurrent.futures.thread
import contextlib
import multiprocessing
import queue
import threading
from collections.abc import Callable, Generator
from typing import Any

from concurim.config import LEVELS
from concurim.instrumentation import aio_primitives as aio
from concurim.instrumentation.aio_taskgroup import AutoTaskGroup
from concurim.instrumentation.aio_tasks import (
    patched_create_task,
    patched_run,
)
from concurim.instrumentation.auto_events import (
    AutoAsyncCondition,
    AutoAsyncEvent,
    AutoCondition,
    AutoEvent,
)
from concurim.instrumentation.auto_mp import AutoPool, AutoProcess
from concurim.instrumentation.auto_support import (
    creation_name,
    in_stdlib,
    user_caller,
)
from concurim.instrumentation.barriers import AutoAsyncBarrier, AutoBarrier
from concurim.instrumentation.executors import TracedThreadPoolExecutor
from concurim.instrumentation.futures_support import traced_as_completed
from concurim.instrumentation.process_pool import TracedProcessPoolExecutor
from concurim.instrumentation.queues import TracedQueue
from concurim.instrumentation.sync import (
    TracedBoundedSemaphore,
    TracedLock,
    TracedRLock,
    TracedSemaphore,
)
from concurim.instrumentation.threads import observe_thread
from concurim.recorder.collector import mark_internal

mark_internal(__file__)

__all__ = ["LEVELS", "auto_instrument"]

_REAL_LOCK = _thread.allocate_lock
_REAL_QUEUE = queue.Queue


class AutoQueue(TracedQueue):
    """``TracedQueue`` named after the line that created it.

    Queues the standard library creates for its own use (a process pool's
    internal work queue, say) are left plain.
    """

    def __new__(cls, maxsize: int = 0):
        if cls is AutoQueue and in_stdlib(1):
            return _REAL_QUEUE(maxsize)
        return super().__new__(cls)

    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize, name=creation_name("Queue"))


def _auto_lock() -> Any:
    if not user_caller(1):
        return _REAL_LOCK()
    return TracedLock(name=creation_name("Lock"))


_REAL_RLOCK = threading.RLock


def _auto_rlock() -> Any:
    if not user_caller(1):
        return _REAL_RLOCK()
    return TracedRLock(name=creation_name("RLock"))


class AutoSemaphore(TracedSemaphore):
    """Traced only when created by user code."""

    def __init__(self, value: int = 1) -> None:
        self._cz_on = user_caller(1)
        super().__init__(
            value, name=creation_name("Semaphore") if self._cz_on else None
        )


class AutoBoundedSemaphore(AutoSemaphore, TracedBoundedSemaphore):
    """Traced only when created by user code."""


class AutoExecutor(TracedThreadPoolExecutor):
    """Traced only when created by user code (not by asyncio, say)."""

    def __init__(self, max_workers: int | None = None, *a: Any, **kw: Any):
        self._cz_on = user_caller(1)
        kw["name"] = creation_name("ThreadPoolExecutor")
        super().__init__(max_workers, *a, **kw)


class AutoProcessPool(TracedProcessPoolExecutor):
    """Traced only when created by user code."""

    def __init__(self, *a: Any, **kw: Any):
        self._cz_on = user_caller(1)
        kw["name"] = creation_name("ProcessPoolExecutor")
        super().__init__(*a, **kw)


class AutoAsyncQueue(aio.TracedAsyncQueue):
    """``TracedAsyncQueue`` named after the line that created it."""

    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize, name=creation_name("Queue"))


class AutoAsyncLock(aio.TracedAsyncLock):
    """``TracedAsyncLock`` named after the line that created it."""

    def __init__(self) -> None:
        super().__init__(name=creation_name("Lock"))


class AutoAsyncSemaphore(aio.TracedAsyncSemaphore):
    """``TracedAsyncSemaphore`` named after the line that created it."""

    def __init__(self, value: int = 1) -> None:
        super().__init__(value, name=creation_name("Semaphore"))


class AutoAsyncBoundedSemaphore(
    AutoAsyncSemaphore, aio.TracedAsyncBoundedSemaphore
):
    """Bounded variant."""


def _wrapped_start(original: Callable[..., Any]) -> Callable[..., Any]:
    def start(self: threading.Thread) -> None:
        observe_thread(self)
        original(self)

    return start


def _patches(level: str) -> list[tuple[Any, str, Any]]:
    """``(owner, attribute, replacement)`` for everything ``level`` patches."""
    rank = LEVELS.index(level)
    out: list[tuple[Any, str, Any]] = []
    if rank >= 1:
        out.append(
            (threading.Thread, "start", _wrapped_start(threading.Thread.start))
        )
    if rank >= 2:
        out.append((queue, "Queue", AutoQueue))
    if rank >= 3:
        out += [
            (threading, "Lock", _auto_lock),
            (threading, "RLock", _auto_rlock),
            (threading, "Semaphore", AutoSemaphore),
            (threading, "BoundedSemaphore", AutoBoundedSemaphore),
            (threading, "Event", AutoEvent),
            (threading, "Condition", AutoCondition),
            (threading, "Barrier", AutoBarrier),
            (concurrent.futures, "ThreadPoolExecutor", AutoExecutor),
            (concurrent.futures.thread, "ThreadPoolExecutor", AutoExecutor),
            (concurrent.futures, "ProcessPoolExecutor", AutoProcessPool),
            (concurrent.futures, "as_completed", traced_as_completed),
            (multiprocessing, "Process", AutoProcess),
            (multiprocessing, "Pool", AutoPool),
            (
                concurrent.futures.process,
                "ProcessPoolExecutor",
                AutoProcessPool,
            ),
        ]
    if rank >= 4:
        loop = asyncio.base_events.BaseEventLoop
        out += [
            (loop, "create_task", patched_create_task(loop.create_task)),
            (asyncio.events.Handle, "_run", patched_run(asyncio.Handle._run)),
            (asyncio, "Queue", AutoAsyncQueue),
            (asyncio, "Lock", AutoAsyncLock),
            (asyncio, "Semaphore", AutoAsyncSemaphore),
            (asyncio, "BoundedSemaphore", AutoAsyncBoundedSemaphore),
            (asyncio, "TaskGroup", AutoTaskGroup),
            (asyncio, "Event", AutoAsyncEvent),
            (asyncio, "Condition", AutoAsyncCondition),
            (asyncio, "Barrier", AutoAsyncBarrier),
        ]
    return out


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
    saved: list[tuple[Any, str, Any]] = []
    try:
        for owner, attr, new in _patches(level):
            saved.append((owner, attr, getattr(owner, attr)))
            setattr(owner, attr, new)
        yield
    finally:
        for owner, attr, old in reversed(saved):
            setattr(owner, attr, old)
