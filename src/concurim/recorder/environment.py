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


# Honest, human-readable statement of what the built-in recorder can and
# cannot see. Stored in every trace and shown by the viewer.
COVERAGE: dict[str, list[str]] = {
    "observed": [
        "Operations on concurim.TracedQueue (put/get/task_done/join/shutdown)",
        "Lifecycle of concurim.TracedThread",
        "Explicit concurim.work() spans and object lineage annotations",
    ],
    "not_observed": [
        "Plain queue.Queue, threading.Lock and other uninstrumented objects",
        "CPU scheduling and GIL ownership (not derivable from these events)",
        "What a worker does between instrumented operations",
        "Child processes (multiprocessing is not instrumented yet)",
    ],
}
