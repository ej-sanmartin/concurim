"""Shared values touched by several actors with no lock in common.

The lockset method (Eraser): a value is *exclusive* while one actor uses it,
which allows unlocked set-up. Once a second actor touches it, every access
must hold some lock that all accesses so far held, the *candidate
lockset*. When the value has been written and that set is empty, no lock
protects it. Unlike the original, the owner's last locks count when it
used any, so "one lock here, another there" is caught while unlocked
set-up is still allowed.

Two refinements keep it from crying wolf. An access that the recorded
events order after every other actor's last access (a queue hand-off, an
event, a condition, a lock passed on, a thread start; see
``hazards_order``) hands the value over: it is exclusive again. A read
made after every other user has ended (reading the result once the
workers are done) is not counted either. A ``join()`` is not an event, so
that last case is covered by "ended" rather than by an edge, and a barrier
is not seen at all. The result is therefore always labelled inferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from concurim.recorder.events import Event
from concurim.replay.hazards_order import Order
from concurim.replay.hazards_util import Found, Labels, ended, name_all
from concurim.replay.state_cells import held_locks


@dataclass
class _Cell:
    owner: str | None = None  # the only actor so far, while exclusive
    owner_locks: set[str] = field(default_factory=set)  # while exclusive
    shared: bool = False
    written: bool = False
    candidates: set[str] = field(default_factory=set)
    # Latest access per actor: (event index, "read"|"write", lock names,
    # the actor's own clock tick at that access).
    last: dict[str, tuple[int, str, list[str], int]] = field(
        default_factory=dict
    )


class CellRaces:
    """Runs the lockset check on each ``cell.read`` and ``cell.write``."""

    def __init__(self) -> None:
        self._cells: dict[str, _Cell] = {}

    def access(
        self, red: Any, ev: Event, i: int, labels: Labels, order: Order
    ) -> list[Found]:
        """Update the cell for this access; report a race the first time."""
        rid, actor = ev.resource_id or "", ev.actor
        if not rid or actor is None or rid not in red.syncs:
            return []
        write = ev.event_type.endswith("write")
        held = held_locks(red, actor)
        names = [red.syncs[h].name for h in held]
        cell = self._cells.setdefault(rid, _Cell())
        op = "write" if write else "read"
        stamp = (i, op, names, order.tick(actor))
        others = [a for a in cell.last if a != actor]
        if not write and others and all(ended(red, a) for a in others):
            cell.last[actor] = stamp
            return []  # the others are done; their end orders this read
        unordered = [
            a for a in others if not order.ordered(a, cell.last[a][3], actor)
        ]
        cell.written = cell.written or write
        if others and not unordered:
            # Every other actor's last access leads up to this one (a
            # hand-off), so the value changes hands instead of being shared.
            cell.owner, cell.owner_locks = actor, set(held)
            cell.shared, cell.candidates = False, set()
            cell.last[actor] = stamp
            return []
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
        cell.last[actor] = stamp
        if not (cell.shared and cell.written and not cell.candidates):
            return []
        other = max(unordered, key=lambda a: cell.last[a][0], default=None)
        if other is None:
            return []
        at, other_op, locks, _ = cell.last[other]
        text = (
            f"{red.syncs[rid].name} is written and used by "
            f"{name_all(labels, [other, actor])} with no lock in common. "
            f"{name_all(labels, [actor])}'s {op} here held "
            f"{_held(names)}; {name_all(labels, [other])}'s {other_op} at "
            f"event {at + 1} held {_held(locks)}. No recorded hand-off "
            "(queue item, event, condition, lock, thread start) orders "
            "them. If a join() or a barrier does, this is not a race; "
            "Concurim cannot see those, so it is a candidate, not proof."
        )
        return [(("race", rid), "unprotected_value", text, True)]


def _held(names: list[str]) -> str:
    return ", ".join(names) if names else "no lock"
