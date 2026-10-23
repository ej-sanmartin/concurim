"""State dataclasses shared by the reducer, engine and explanations."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from itertools import islice
from typing import Any

ITEMS_HEAD = 64  # queued item ids kept per frame


@dataclass
class ThreadState:
    id: str
    name: str
    status: str = "running"  # running | waiting | working | finished | failed
    basis: str = "inferred"  # observed | inferred
    waiting_on: dict[str, str] | None = None
    holding: list[str] = field(default_factory=list)
    work: str | None = None


@dataclass
class QueueState:
    id: str
    name: str
    maxsize: int = 0
    items: deque[str] = field(default_factory=deque)
    unfinished: int = 0
    shutdown: str | None = None  # None | graceful | immediate
    blocked_puts: list[dict[str, str | None]] = field(default_factory=list)
    blocked_gets: list[dict[str, str | None]] = field(default_factory=list)
    joiners: list[str] = field(default_factory=list)


@dataclass
class ObjectState:
    id: str
    type: str | None = None
    preview: str | None = None
    parent: str | None = None
    # new | putting | queued | held | released | discarded
    phase: str = "new"
    at: str | None = None  # id of the thread or queue it is at


@dataclass
class Applied:
    """What one event changed, plus facts for the explanation."""

    threads: set[str] = field(default_factory=set)
    queues: set[str] = field(default_factory=set)
    objects: set[str] = field(default_factory=set)
    motion: dict[str, str | None] | None = None
    facts: dict[str, Any] = field(default_factory=dict)


def snapshot(state: Any) -> dict[str, Any]:
    """JSON-ready copy of a state dataclass.

    Much cheaper than ``dataclasses.asdict``: fields are scalars, lists of
    scalars/small dicts, or small dicts, so a shallow copy of each suffices.
    """
    out: dict[str, Any] = {}
    if isinstance(state, QueueState):
        # Frames carry only the head of long queues (the viewer draws at most
        # a handful of slots); ``size`` is always the true occupancy.
        out["size"] = len(state.items)
    for key, value in vars(state).items():
        if key == "items":
            continue
        if isinstance(value, list):
            out[key] = [dict(v) if isinstance(v, dict) else v for v in value]
        elif isinstance(value, dict):
            out[key] = dict(value)
        else:
            out[key] = value
    if isinstance(state, QueueState):
        out["items"] = list(islice(state.items, ITEMS_HEAD))
    return out
