"""Interpreter and platform facts needed to interpret a trace."""

from __future__ import annotations

import os
import platform
import sys
import sysconfig
from typing import Any

from concurim.config import LEVELS


def environment_info() -> dict[str, Any]:
    """Describe the interpreter.

    ``free_threaded_build`` is a *build* capability; ``gil_enabled`` is the
    *runtime* state (a free-threaded build may still run with the GIL on).
    ``gil_enabled`` is ``None`` when the interpreter cannot tell.
    """
    is_gil_enabled = getattr(sys, "_is_gil_enabled", None)
    return {
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "free_threaded_build": bool(
            sysconfig.get_config_var("Py_GIL_DISABLED")
        ),
        "gil_enabled": is_gil_enabled() if is_gil_enabled else None,
        "platform": platform.system(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
    }


def coverage_for(auto: str) -> dict[str, list[str]]:
    """Honest statement of what a recording at level ``auto`` can see.

    Stored in every trace and shown by the viewer; ``not_observed`` is as
    important as ``observed``.
    """
    rank = LEVELS.index(auto)
    observed = [
        "Operations on concurim.TracedQueue, TracedLock, TracedSemaphore, "
        "TracedEvent, TracedCondition and TracedThreadPoolExecutor, when "
        "the program uses them",
        "Lifecycle of concurim.TracedThread, when used",
        "Explicit concurim.work() spans and lineage annotations, when used",
        "With source included: the line each worker is on, sampled every "
        "few milliseconds (approximate)",
    ]
    not_observed = [
        "CPU scheduling and GIL ownership (not derivable from these events)",
        "What a worker does between instrumented operations, except the "
        "sampled line (short-lived lines can be missed)",
        "Anything inside child processes; multiprocessing is seen only "
        "through ProcessPoolExecutor, at the sync level and above",
    ]
    if rank >= 1:
        observed.append(
            "Start, finish and failure of every threading.Thread started "
            "during the run, including subclasses that override run()"
        )
    if rank >= 2:
        observed.append(
            "queue.Queue objects created during the run "
            "(put/get/task_done/join/shutdown)"
        )
        not_observed.append(
            "Queues created before recording, LifoQueue, PriorityQueue "
            "and SimpleQueue"
        )
    else:
        not_observed.append(
            "Plain queue.Queue contents and operations (use the queue "
            "instrumentation level, or concurim.TracedQueue)"
        )
    if rank >= 3:
        observed.append(
            "threading Lock, RLock, Semaphore, BoundedSemaphore, Event, "
            "Condition, Barrier, "
            "ThreadPoolExecutor and ProcessPoolExecutor (submit, and task "
            "start/end as reported by each worker process) created by the "
            "program's own code"
        )
        not_observed.append(
            "Locks and executors created inside libraries or the standard "
            "library, and any created before recording"
        )
    else:
        not_observed.append(
            "Plain threading locks, semaphores, events, conditions, "
            "barriers and executors (use the sync instrumentation level, "
            "or the Traced* classes)"
        )
    if rank >= 4:
        observed.append(
            "asyncio tasks (creation, each step the event loop runs, end) "
            "and asyncio Queue, Lock, Semaphore, BoundedSemaphore, Event, "
            "Condition and Barrier created during the run"
        )
        not_observed.append(
            "What an asyncio task awaits when it is not one of the above "
            "(sleep, I/O, futures), eagerly started tasks' first step, "
            "and loops other than the standard one"
        )
    else:
        not_observed.append("asyncio tasks and their primitives")
    if rank == 0:
        not_observed.append("Plain threading.Thread objects")
    return {"observed": observed, "not_observed": not_observed}
