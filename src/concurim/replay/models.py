"""State dataclasses shared by the reducer, engine and explanations."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from itertools import islice
from typing import Any

ITEMS_HEAD = 64  # queued item ids kept per frame


def actor_kind(task_id: str | None, metadata: dict[str, Any]) -> str:
    """``task`` for asyncio tasks, ``process`` for pool workers, else
    ``thread``."""
    if task_id:
        return "task"
    return "process" if metadata.get("actor_kind") == "process" else "thread"


@dataclass
class ThreadState:
    id: str
    name: str
    # running | waiting | working | suspended | finished | failed | cancelled
    status: str = "running"
    basis: str = "inferred"  # observed | inferred
    # {"resource": id, "op": "put" | "get" | "join" | "acquire"}
    waiting_on: dict[str, str] | None = None
    holding: list[str] = field(default_factory=list)
    work: str | None = None
    kind: str = "thread"  # thread | task (asyncio) | process (pool worker)


@dataclass
class QueueState:
    id: str
    name: str
    maxsize: int = 0
    items: deque[str] = field(default_factory=deque)
    unfinished: int = 0
    shutdown: str | None = None  # None | graceful | immediate
    kind: str = "queue"  # queue | executor (a pool's pending-task queue)
    workers: int = 0  # executor: max_workers
    running: int = 0  # executor: tasks currently executing
    blocked_puts: list[dict[str, str | None]] = field(default_factory=list)
    blocked_gets: list[dict[str, str | None]] = field(default_factory=list)
    joiners: list[str] = field(default_factory=list)


@dataclass
class SyncState:
    """A lock, semaphore, event, condition or task group."""

    id: str
    name: str
    # lock | rlock | semaphore | event | condition | taskgroup
    kind: str = "lock"
    capacity: int = 1  # permits at creation
    value: int = 1  # permits available now (semaphores)
    holders: list[str] = field(default_factory=list)  # one per hold
    waiters: list[dict[str, str | None]] = field(default_factory=list)
    is_set: bool = False  # event: the flag
    lock: str | None = None  # condition: id of its associated lock
    notified: int = 0  # condition: signalled waiters not yet resumed
    members: list[str] = field(default_factory=list)  # taskgroup: tasks
    running: int = 0  # taskgroup: member tasks not finished


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
    syncs: set[str] = field(default_factory=set)
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


def resume(th: ThreadState) -> None:
    """Status after a wait ends: back inside work, or merely not blocked."""
    if th.work:
        th.status, th.basis = "working", "observed"
    else:
        th.status, th.basis = "running", "inferred"
