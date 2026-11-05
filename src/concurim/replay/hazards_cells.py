"""Shared values touched by several actors with no lock in common.

The lockset method (Eraser): a value is *exclusive* while one actor uses it,
which allows unlocked set-up. Once a second actor touches it, every access
must hold some lock that all accesses so far held, the *candidate
lockset*. When the value has been written and that set is empty, no lock
protects it. Unlike the original, the owner's last locks count when it
used any, so "one lock here, another there" is caught while unlocked
set-up is still allowed. A read made after every other user of the value
has ended (reading the result once the workers are done) is not counted:
their end already orders it. Locks come from the lock events, so they are
as exact as those. What this cannot see is ordering by a queue hand-off or
an event, so the result is always labelled inferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from concurim.recorder.events import Event
from concurim.replay.hazards_util import Found, Labels, ended, name_all
from concurim.replay.state_cells import held_locks


@dataclass
class _Cell:
    owner: str | None = None  # the only actor so far, while exclusive
    owner_locks: set[str] = field(default_factory=set)  # while exclusive
    shared: bool = False
    written: bool = False
    candidates: set[str] = field(default_factory=set)
    # Latest access per actor: (event index, "read"|"write", lock names).
    last: dict[str, tuple[int, str, list[str]]] = field(default_factory=dict)


class CellRaces:
    """Runs the lockset check on each ``cell.read`` and ``cell.write``."""

    def __init__(self) -> None:
        self._cells: dict[str, _Cell] = {}

    def access(
        self, red: Any, ev: Event, i: int, labels: Labels
    ) -> list[Found]:
        """Update the cell for this access; report a race the first time."""
        rid, actor = ev.resource_id or "", ev.actor
        if not rid or actor is None or rid not in red.syncs:
            return []
        write = ev.event_type.endswith("write")
        held = held_locks(red, actor)
        names = [red.syncs[h].name for h in held]
        cell = self._cells.setdefault(rid, _Cell())
        others = [a for a in cell.last if a != actor]
        if not write and others and all(ended(red, a) for a in others):
            cell.last[actor] = (i, "read", names)
            return []  # the others are done; their end orders this read
        cell.written = cell.written or write
        if cell.owner is None:
            cell.owner = actor
        if not cell.shared and actor == cell.owner:
            cell.owner_locks = set(held)
        elif not cell.shared:
            cell.shared = True
            cell.candidates = set(held)
            if cell.owner_locks:
                cell.candidates &= cell.owner_locks
        elif cell.shared:
            cell.candidates &= set(held)
        cell.last[actor] = (i, "write" if write else "read", names)
        if not (cell.shared and cell.written and not cell.candidates):
            return []
        other = max(
            (a for a in cell.last if a != actor),
            key=lambda a: cell.last[a][0],
            default=None,
        )
        if other is None:
            return []
        at, op, locks = cell.last[other]
        text = (
            f"{red.syncs[rid].name} is written and used by "
            f"{name_all(labels, [other, actor])} with no lock in common. "
            f"{name_all(labels, [actor])}'s {cell.last[actor][1]} here held "
            f"{_held(names)}; {name_all(labels, [other])}'s {op} at event "
            f"{at + 1} held {_held(locks)}. If nothing else orders them (a "
            "join, a queue hand-off, an event), this is a data race. "
            "Concurim cannot see those orderings, so it is a candidate, "
            "not proof."
        )
        return [(("race", rid), "unprotected_value", text, True)]


def _held(names: list[str]) -> str:
    return ", ".join(names) if names else "no lock"
