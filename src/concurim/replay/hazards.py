"""Fail states read off one recorded run.

Each detector looks at the replay state right after an event and says what
that state means: a lock whose holder ended, two locks taken in opposite
order, a coroutine stuck on a thread lock, a ``fork`` that copied a held
lock, a wait nobody is left to end, or a shared value touched with no lock
in common. A hazard is a sentence plus whether it is *inferred*: an
inferred one rests on history ("every thread that ever put here has ended")
or on a pattern ("opposite lock order can deadlock"), not on a block this
run actually showed. Nothing here searches other schedules.
"""

from __future__ import annotations

from typing import Any

from concurim.recorder.events import Event
from concurim.recorder.events import EventType as E
from concurim.replay.hazards_cells import CellRaces
from concurim.replay.hazards_order import Order
from concurim.replay.hazards_signals import Signals
from concurim.replay.hazards_util import (
    Found,
    Labels,
    ended,
    join_names,
    verb,
)
from concurim.replay.wait_for import actor_labels

LOCKS = ("lock", "rlock")
HELD = (*LOCKS, "semaphore")
_ENDERS = {
    E.THREAD_FINISHED,
    E.THREAD_FAILED,
    E.TASK_FINISHED,
    E.TASK_FAILED,
    E.TASK_CANCELLED,
}
_TIMED_END = (".completed", ".failed", ".timeout")

PATTERN_NOTE = (
    "This is a pattern seen in this run, not a block that happened. "
    "Concurim does not search other schedules."
)


def _timed(ev: Event) -> bool:
    """Whether the call has a timeout, so it cannot wait forever."""
    timeout = ev.metadata.get("timeout")
    return timeout is not None and timeout != -1


class Hazards:
    """Remembers what each event revealed; ``observe`` is called in order."""

    def __init__(self) -> None:
        self.found: list[dict[str, Any]] = []
        self._seen: set[tuple[Any, ...]] = set()
        self._async: set[str] = set()  # asyncio locks and semaphores
        self._order: dict[tuple[str, str], dict[str, int]] = {}
        self._timed: set[str] = set()  # ops that cannot wait forever
        self._signals = Signals()
        self._cells = CellRaces()
        self._clocks = Order()

    def observe(self, red: Any, ev: Event, i: int) -> list[dict[str, Any]]:
        """Hazards event ``i`` reveals (new ones only)."""
        t = ev.event_type
        op = ev.operation_id
        if op and t.endswith(_TIMED_END):
            self._timed.discard(op)
        elif op and t.endswith(".started") and _timed(ev):
            self._timed.add(op)
        if t.endswith(".created") and ev.metadata.get("asyncio"):
            self._async.add(ev.resource_id or "")
        self._signals.note(ev)
        self._clocks.observe(red, ev)
        before = len(self.found)
        names = None  # computed only when a hazard needs it

        def labels() -> dict[str, str]:
            nonlocal names
            if names is None:
                names = actor_labels(red)
            return names

        found: list[Found] = []
        if t == E.LOCK_ACQUIRE_STARTED:
            found += self._lock_order(red, ev, i, labels)
        if t in (E.LOCK_ACQUIRE_BLOCKED, E.SEMAPHORE_ACQUIRE_BLOCKED):
            found += self._loop_blocked(red, ev, labels)
        if t in _ENDERS or t in (
            E.LOCK_ACQUIRE_BLOCKED,
            E.SEMAPHORE_ACQUIRE_BLOCKED,
        ):
            found += self._holder_gone(red, labels)
        if t in (E.THREAD_START_REQUESTED, E.EXECUTOR_CREATED):
            found += self._fork_with_lock(red, ev, labels)
        if t in (E.CELL_READ, E.CELL_WRITE):
            found += self._cells.access(red, ev, i, labels, self._clocks)
        self._add(found, i)
        return self.found[before:]

    def finish(self, red: Any, last: int) -> list[dict[str, Any]]:
        """Hazards only the final state shows (waits left open at the end)."""
        before = len(self.found)
        self._add(
            self._signals.at_end(red, self._timed, lambda: actor_labels(red)),
            last,
        )
        return self.found[before:]

    def _add(self, found: list[Found], i: int) -> None:
        """Keep each new hazard once, remembering where it showed up."""
        for key, kind, text, inferred in found:
            if key not in self._seen:
                self._seen.add(key)
                self.found.append(
                    {"kind": kind, "at": i, "text": text, "inferred": inferred}
                )

    # -- locks ------------------------------------------------------------

    def _holder_gone(self, red: Any, labels: Labels) -> list[Found]:
        """A lock whose every holder ended while someone waits for it."""
        out = []
        for s in red.syncs.values():
            if s.kind not in HELD or not s.waiters or not s.holders:
                continue
            if s.kind == "semaphore" and s.capacity < 1:
                continue  # a signalling semaphore is released by others
            holders = list(dict.fromkeys(s.holders))
            if not all(ended(red, h) for h in holders):
                continue
            waiters = list(
                dict.fromkeys(
                    w["thread"]
                    for w in s.waiters
                    if w.get("thread") and w.get("op") not in self._timed
                )
            )
            if not waiters:
                continue
            names = labels()
            text = (
                f"{join_names([names.get(w, w) for w in waiters])} "
                f"{verb(waiters, 'waits', 'wait')} for {s.name}, "
                f"but {join_names([names.get(h, h) for h in holders])} "
                f"ended while holding it. No running thread holds it now, "
                "so it stays taken unless some other thread releases it."
            )
            out.append(
                (
                    ("holder_gone", s.id, tuple(holders)),
                    "holder_gone",
                    text,
                    False,
                )
            )
        return out

    def _lock_order(
        self, red: Any, ev: Event, i: int, labels: Labels
    ) -> list[Found]:
        """Two locks taken in opposite order by different actors."""
        s = red.syncs.get(ev.resource_id or "")
        actor = ev.actor
        if (
            s is None
            or s.kind not in LOCKS
            or actor is None
            or actor in s.holders  # re-entry: not a new ordering
            or ev.metadata.get("blocking") is False
        ):
            return []
        out = []
        for held in red.syncs.values():
            if held.id == s.id or held.kind not in LOCKS:
                continue
            if actor not in held.holders:
                continue
            self._order.setdefault((held.id, s.id), {}).setdefault(actor, i)
            for other, at in self._order.get((s.id, held.id), {}).items():
                if other == actor:
                    continue
                names = labels()
                text = (
                    f"{names.get(other, other)} waited for {held.name} "
                    f"while holding {s.name} (event {at + 1}), and "
                    f"{names.get(actor, actor)} waited for {s.name} while "
                    f"holding {held.name} (event {i + 1}). Two threads that "
                    "take two locks in opposite order can deadlock if each "
                    "takes its first lock before the other takes its second."
                )
                key = ("lock_order", *sorted((held.id, s.id)))
                out.append((key, "lock_order", text, True))
        return out

    def _loop_blocked(self, red: Any, ev: Event, labels: Labels) -> list[Found]:
        """A task waiting on a threading lock stops its whole event loop."""
        actor = ev.actor
        th = red.threads.get(actor or "")
        s = red.syncs.get(ev.resource_id or "")
        if th is None or th.kind != "task" or s is None:
            return []
        if s.id in self._async or ev.operation_id in self._timed:
            return []
        names = labels()
        text = (
            f"{names.get(th.id, th.id)} is an asyncio task and blocked on "
            f"{s.name}, a threading lock. A blocked task stops its whole "
            "event loop thread, so no other task on that loop runs until "
            "the lock is free. Use asyncio.Lock inside coroutines, or move "
            "the blocking code to an executor."
        )
        return [(("loop_blocked", s.id, th.id), "loop_blocked", text, False)]

    def _held_here(self, red: Any, actor: str) -> bool:
        """Whether ``actor`` lives in the process that is about to fork.

        Another process keeps its hold. Fork copies only this process,
        so that hold is not left taken with nobody left to free it.
        """
        holder = red.threads.get(actor)
        return holder is None or holder.kind != "process"

    def _fork_with_lock(
        self, red: Any, ev: Event, labels: Labels
    ) -> list[Found]:
        """A child started by ``fork`` inherits locks other threads here hold.

        A lock held by another process is shared, or is that process's
        own copy. Covers ``Process`` (``start.requested``) and the
        workers of a ``Pool`` (``executor.created``).
        """
        meta = ev.metadata
        if meta.get("start_method") != "fork":
            return []
        if meta.get("process"):
            child = str(meta.get("child_name", "A child process"))
            start = f"{child} is started"
        elif meta.get("pool") == "process":
            pool = red.queues.get(ev.resource_id or "")
            child = f"The workers of {pool.name if pool else 'a process pool'}"
            start = f"{child} are started"
        else:
            return []
        out = []
        for s in red.syncs.values():
            if s.kind not in LOCKS:
                continue
            others = [
                h
                for h in dict.fromkeys(s.holders)
                if h != ev.actor
                and not ended(red, h)
                and self._held_here(red, h)
            ]
            if not others:
                continue
            names = labels()
            text = (
                f"{start} by fork while {s.name} is held by "
                f"{join_names([names.get(h, h) for h in others])}. Each "
                f"child gets its own copy of {s.name}, still taken, and the "
                "holder does not exist there, so a child that takes it "
                "waits forever. Start with spawn or forkserver, or release "
                "it first."
            )
            out.append((("fork_lock", s.id, child), "fork_lock", text, False))
        return out


def hazard_warnings(found: list[dict[str, Any]]) -> list[str]:
    """One line per hazard for the viewer's warning list."""
    return [f"At event {h['at'] + 1}, {h['text']}" for h in found]
