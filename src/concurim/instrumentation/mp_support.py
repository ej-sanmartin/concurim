"""Shared plumbing for observing work in other processes.

Each worker reports when a task starts and ends through a pipe it inherits
at start-up; a thread in the parent turns those reports into events,
attributed to a logical actor per worker process. No pickling of recorder
state happens: only small tuples of primitives cross the pipe.

When sampling is on, the worker reports the user function it entered (on
its own thread, so a tight task cannot finish unseen) and later lines from
a background sampler.

Honest limits: events from workers are stamped when the parent *receives*
them (the worker's own clock reading is kept in ``child_ns``). Sizes are
what ``pickle`` produces for the value; they are measured in addition to
the pool's own copy, so recording costs one extra pickle per value.
"""

from __future__ import annotations

import contextlib
import multiprocessing
import multiprocessing.connection
import multiprocessing.managers
import multiprocessing.queues
import multiprocessing.shared_memory
import multiprocessing.sharedctypes
import multiprocessing.synchronize
import os
import pickle
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from concurim.instrumentation.threads import PLUMBING_FILES
from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.events import Source
from concurim.recorder.lifecycle import forget_recorder
from concurim.recorder.sampler import LineSampler, entry_profile

mark_internal(__file__)
PLUMBING_FILES.add(__file__)  # the report-reading thread is not the workload

# Objects that cross a process boundary as a handle to the same memory or
# channel, not as a private copy.
_SHARED = (
    multiprocessing.sharedctypes.SynchronizedBase,
    multiprocessing.shared_memory.SharedMemory,
    multiprocessing.shared_memory.ShareableList,
    multiprocessing.managers.BaseProxy,
    multiprocessing.synchronize.SemLock,
    multiprocessing.synchronize.Event,
    multiprocessing.synchronize.Condition,
    multiprocessing.synchronize.Barrier,
    multiprocessing.queues.Queue,
    multiprocessing.queues.SimpleQueue,
    multiprocessing.connection.Connection,
)

# Set in each worker process by ``child_init`` and ``child_call``.
_CHILD_QUEUE: Any = None
_CURRENT_OP: str | None = None
_SAMPLE_ROOT: str | None = None


def pickled_size(value: Any) -> int | None:
    """Bytes ``pickle`` needs for ``value``, or ``None`` if it cannot."""
    try:
        return len(pickle.dumps(value, pickle.HIGHEST_PROTOCOL))
    except Exception:  # noqa: BLE001 - sizing must never break the program
        return None


def _shared_types(value: Any) -> list[str]:
    """Type names of shared objects in ``value`` or one level inside it."""
    if isinstance(value, _SHARED):
        return [type(value).__name__]
    items: Any = ()
    if isinstance(value, dict):
        items = value.values()
    elif isinstance(value, list | tuple | set | frozenset):
        items = value
    return [type(v).__name__ for v in items if isinstance(v, _SHARED)]


def describe_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict:
    """Metadata telling which arguments are copied and which are shared.

    A copied argument is pickled and rebuilt in the worker, so changes the
    worker makes to it are invisible to the parent. A shared one (shared
    ctypes, shared memory, manager proxy, multiprocessing queue or lock)
    reaches the same underlying object. Containers are looked into one
    level deep.
    """
    shared: list[str] = []
    copied = size = 0
    for value in (*args, *kwargs.values()):
        found = _shared_types(value)
        if found:
            shared.extend(found)
            continue
        copied += 1
        size += pickled_size(value) or 0
    meta: dict[str, Any] = {"copied_args": copied, "shared_args": len(shared)}
    if copied:
        meta["copied_bytes"] = size
    if shared:
        meta["shared_types"] = ", ".join(sorted(set(shared)))
    return meta


# -- worker side --------------------------------------------------------------


def child_init(
    queue: Any,
    init: Callable[..., Any] | None,
    args: Any,
    sampling: tuple[str, float] | None,
) -> None:
    """Runs first in every worker: remember the pipe, then the user's init.

    ``sampling`` is ``(source root, seconds between samples)`` or ``None``.
    """
    global _CHILD_QUEUE, _SAMPLE_ROOT
    _CHILD_QUEUE = queue
    _SAMPLE_ROOT = None
    forget_recorder()  # a forked worker inherits the parent's recorder
    if sampling is not None:
        _SAMPLE_ROOT = sampling[0]
        main = threading.get_ident()
        LineSampler(
            sampling[0],
            sampling[1],
            lambda ident: _CURRENT_OP if ident == main else None,
            lambda op, file, line, name: report(
                "line", op, where=(file, line, name)
            ),
        ).start()
    if init is not None:
        init(*args)


def report(
    kind: str,
    op: str,
    error: str | None = None,
    where: tuple[str, int, str] | None = None,
    size: int | None = None,
) -> None:
    """Send one report to the parent; never let it break the task."""
    queue = _CHILD_QUEUE
    if queue is None:
        return
    name = multiprocessing.current_process().name
    # Recording must never alter or break the program being recorded.
    with contextlib.suppress(Exception):
        queue.put(
            (
                kind,
                op,
                os.getpid(),
                name,
                time.perf_counter_ns(),
                error,
                where,
                size,
            )
        )


def _emit_line(filename: str, line: int, qualname: str) -> None:
    """Report one sampled line for the task running in this worker."""
    op = _CURRENT_OP
    if op is not None:
        report("line", op, where=(filename, line, qualname))


def child_call(
    op: str,
    fn: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Run ``fn`` in the worker, reporting start and outcome."""
    global _CURRENT_OP
    report("started", op)
    _CURRENT_OP = op  # after "started", so no sample precedes it
    hook = None
    if _SAMPLE_ROOT is not None and sys.getprofile() is None:
        hook = entry_profile(_SAMPLE_ROOT, _emit_line)
        sys.setprofile(hook)
    try:
        result = fn(*args, **kwargs)
    except BaseException as error:
        _CURRENT_OP = None
        report("failed", op, type(error).__name__)
        raise
    else:
        _CURRENT_OP = None
        report(
            "finished",
            op,
            size=None if result is None else pickled_size(result),
        )
        return result
    finally:
        # Leave a profile the task installed itself.
        if hook is not None and sys.getprofile() is hook:
            sys.setprofile(None)


# -- parent side --------------------------------------------------------------

_SYNC = "sync"  # queue marker: not a report tuple


class Sink:
    """Parent-side receiver of worker reports; subclasses make the events.

    Args:
        rec: The active recorder.
        ctx: Multiprocessing context the workers are created from.
    """

    def __init__(self, rec: Recorder, ctx: Any) -> None:
        self.rec = rec
        self.queue = ctx.SimpleQueue()
        self.actors: list[str] = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._closed = False
        self._synced = threading.Event()

    def start(self) -> None:
        """Begin turning reports into events."""
        self._thread.start()

    def close(self) -> None:
        """Flush every report already sent, then stop (once)."""
        if self._closed:
            return
        self._closed = True
        self.queue.put(None)
        self._thread.join()

    def actor(self, pid: int, name: str) -> str:
        """Logical actor for the worker with this pid (registered once)."""
        actor = self.rec.remote_actor(str(pid), name, pid)
        if actor not in self.actors:
            self.actors.append(actor)
        return actor

    def line(self, actor: str, where: tuple[str, int, str] | None) -> None:
        """Record one sampled line of the task running in ``actor``."""
        if where is not None:
            file, line, function = where
            self.rec.emit_as(
                actor,
                E.CODE_SAMPLED,
                source=Source(self.rec.display_path(file), line, function),
            )

    def handle(self, report_: tuple[Any, ...]) -> None:
        """Turn one report into events."""
        raise NotImplementedError

    def sync(self, timeout: float = 2.0) -> None:
        """Wait until every report already sent has been handled.

        Args:
            timeout: Seconds to wait at most; the reader may be slow.
        """
        if self._closed or not self._thread.is_alive():
            return
        self._synced.clear()
        self.queue.put(_SYNC)
        self._synced.wait(timeout)

    def _run(self) -> None:
        while (item := self.queue.get()) is not None:
            if item == _SYNC:
                self._synced.set()
            else:
                self.handle(item)
