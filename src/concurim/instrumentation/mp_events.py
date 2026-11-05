"""Lock and value events reported by worker processes.

A worker has no recorder of its own. It sends each event through the pipe
it inherited (see ``mp_support``) and the parent's reader thread records
it on behalf of that worker. Only scalars cross the pipe. The parent stamps
the event when it *receives* it, so the order between two different
processes is approximate; the order within one process is exact.
"""

from __future__ import annotations

import contextlib
import itertools
import multiprocessing
import os
import sys
import time
from typing import Any

from concurim.recorder.collector import INTERNAL_FILES, mark_internal
from concurim.recorder.events import Source

mark_internal(__file__)

KIND = "ev"  # first field of the tuples this module sends
_OPS = itertools.count(1)
_RAW_TYPES = (bool, int, float, str)
_RAW_MAX = 256


def reporting() -> bool:
    """Whether this process has a pipe to report through."""
    from concurim.instrumentation import mp_support

    return mp_support._CHILD_QUEUE is not None


def child_op() -> str:
    """An operation id that cannot collide with another process's."""
    return f"{os.getpid()}-op-{next(_OPS)}"


def caller_where() -> tuple[str, int, str] | None:
    """File, line and function of the nearest frame outside Concurim."""
    frame = sys._getframe(1)
    while frame is not None and frame.f_code.co_filename in INTERNAL_FILES:
        frame = frame.f_back
    if frame is None:
        return None
    code = frame.f_code
    return code.co_filename, frame.f_lineno, code.co_qualname


def raw_meta(value: Any) -> dict[str, Any]:
    """Metadata for a value seen in a worker.

    The text is sent only for plain built-in types. The parent decides
    whether it becomes a preview (previews are off by default) and applies
    its redaction rules, so the worker needs no copy of the settings.
    """
    meta: dict[str, Any] = {"value_type": type(value).__name__}
    if type(value) in _RAW_TYPES:
        meta["raw"] = str(value)[:_RAW_MAX]
    return meta


def report_event(
    event_type: str,
    rid: str,
    op: str,
    meta: dict[str, Any],
    where: tuple[str, int, str] | None,
) -> None:
    """Send one event to the parent; never let it break the program."""
    from concurim.instrumentation import mp_support

    queue = mp_support._CHILD_QUEUE
    if queue is None:
        return
    with contextlib.suppress(Exception):
        queue.put(
            (
                KIND,
                event_type,
                os.getpid(),
                multiprocessing.current_process().name,
                time.perf_counter_ns(),
                rid,
                op,
                meta,
                where,
            )
        )


def record_remote(sink: Any, item: tuple[Any, ...]) -> None:
    """Parent side: turn one reported event into a recorded event."""
    _kind, event_type, pid, pname, _ns, rid, op, meta, where = item
    rec = sink.rec
    meta = dict(meta)
    raw = meta.pop("raw", None)
    if raw is not None:
        info = rec.describe_payload(raw)  # applies preview and redaction
        if "preview" in info:
            meta["preview"] = info["preview"]
    source = None
    if where is not None:
        file, line, function = where
        source = Source(rec.display_path(file), line, function)
    rec.emit_as(
        sink.actor(pid, pname),
        event_type,
        resource_id=rid,
        operation_id=op,
        source=source,
        metadata=meta,
    )
