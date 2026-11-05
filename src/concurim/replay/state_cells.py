"""Reducer handlers for tracked shared values ("cells").

A cell lives in ``SyncState`` (kind ``cell``) so the viewer draws it like
any other shared resource. It keeps the current value (only when previews
are on) and the latest accesses: who, read or write, when, and which locks
that actor held at that moment. Held locks come from the lock state at
the access, so they are as exact as the lock events themselves.
"""

from __future__ import annotations

from typing import Any

from concurim.recorder.events import EventType as E
from concurim.replay.models import SyncState

MAX_ACCESSES = 8  # per cell, newest last
HELD_KINDS = ("lock", "rlock")


def held_locks(red: Any, actor: str) -> list[str]:
    """Ids of the locks ``actor`` holds now, in creation order."""
    return [
        s.id
        for s in red.syncs.values()
        if (s.kind in HELD_KINDS or (s.kind == "semaphore" and s.capacity == 1))
        and actor in s.holders
    ]


def _created(red: Any, ev, app, th):
    rid = ev.resource_id or "cell-?"
    s = red.syncs.setdefault(rid, SyncState(rid, ""))
    s.name = str(ev.metadata.get("name", rid))
    s.kind = "cell"
    s.preview = ev.metadata.get("preview")
    app.syncs.add(rid)


def _access(red: Any, ev, app, th):
    s = red.sync(ev, app)
    write = ev.event_type == E.CELL_WRITE
    held = held_locks(red, th.id)
    app.facts.update(
        write=write,
        previous=s.preview,
        preview=ev.metadata.get("preview", s.preview),
        value_type=ev.metadata.get("value_type"),
        lock_names=[red.syncs[h].name for h in held],
    )
    if "preview" in ev.metadata:
        s.preview = ev.metadata["preview"]
    s.accesses.append(
        {
            "actor": th.id,
            "op": "write" if write else "read",
            "t": ev.timestamp_ns,
            "locks": held,
        }
    )
    del s.accesses[:-MAX_ACCESSES]


CELL_HANDLERS: dict[str, Any] = {
    E.CELL_CREATED: _created,
    E.CELL_READ: _access,
    E.CELL_WRITE: _access,
}
