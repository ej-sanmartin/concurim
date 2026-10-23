"""Interpreter and platform facts needed to interpret a trace."""

from __future__ import annotations

import os
import platform
import sys
import sysconfig
from typing import Any


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
    observed = [
        "Operations on concurim.TracedQueue, when the program uses it",
        "Lifecycle of concurim.TracedThread, when used",
        "Explicit concurim.work() spans and lineage annotations, when used",
    ]
    not_observed = [
        "CPU scheduling and GIL ownership (not derivable from these events)",
        "What a worker does between instrumented operations",
        "Child processes (multiprocessing is not instrumented yet)",
        "threading locks, events, conditions, semaphores and executors",
    ]
    if auto in ("threads", "queues"):
        observed.append(
            "Start, finish and failure of every threading.Thread started "
            "during the run, including subclasses that override run()"
        )
    if auto == "queues":
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
    if auto == "none":
        not_observed.append("Plain threading.Thread objects")
    return {"observed": observed, "not_observed": not_observed}
