"""Waits that no remaining thread is known to end.

A wait on a queue, event or condition ends when somebody puts, sets or
notifies. Concurim remembers who ever did, and says so when the run ends
with a waiter left and all of them gone. That rests on history (a thread
that never touched the resource could still signal), so it is *inferred*.
The ``join()`` case is arithmetic on counts the run showed, so it is not.
Both are judged on the final state: a consumer idle for a moment before
``shutdown()`` is normal, one still idle at the end is not.
"""

from __future__ import annotations

from typing import Any

from concurim.recorder.events import Event
from concurim.recorder.events import EventType as E
from concurim.replay.hazards_util import (
    ENDED,
    Found,
    Labels,
    ended,
    name_all,
    verb,
)

_SIGNALS = {E.QUEUE_PUT_COMPLETED, E.EVENT_SET, E.CONDITION_NOTIFY}
# kind -> (method name, what a sender does, in the third person)
_SENDS = {"event": ("set", "sets"), "condition": ("notify", "notifies")}


def _untimed(waiters: Any, timed: set[str]) -> list[str]:
    """Waiting actors whose call has no timeout (so could wait forever)."""
    return list(
        dict.fromkeys(
            w["thread"]
            for w in waiters
            if w.get("thread") and w.get("op") not in timed
        )
    )


class Signals:
    """Who has signalled each resource, and what that implies for waiters."""

    def __init__(self) -> None:
        self._senders: dict[str, dict[str, None]] = {}

    def note(self, ev: Event) -> None:
        """Remember who put, set or notified."""
        if ev.event_type in _SIGNALS and ev.resource_id and ev.actor:
            self._senders.setdefault(ev.resource_id, {})[ev.actor] = None

    def at_end(self, red: Any, timed: set[str], labels: Labels) -> list[Found]:
        """Hazards among the waits still open when the run ended."""
        out: list[Found] = []
        for q in red.queues.values():
            if q.kind == "queue":
                out += self._queue_gets(red, q, timed, labels)
                out += self._join(red, q, labels)
        for s in red.syncs.values():
            if s.kind in _SENDS:
                out += self._sync_wait(red, s, timed, labels)
        return out

    def _stranded(self, red: Any, rid: str) -> list[str] | None:
        """Past senders of ``rid`` when every one has ended, else ``None``."""
        senders = list(self._senders.get(rid, ()))
        if not senders or not all(ended(red, a) for a in senders):
            return None
        return senders

    def _queue_gets(
        self, red: Any, q: Any, timed: set[str], labels: Labels
    ) -> list[Found]:
        waiters = _untimed(q.blocked_gets, timed)
        senders = self._stranded(red, q.id)
        if not waiters or q.items or q.shutdown or senders is None:
            return []
        text = (
            f"The run ended with {name_all(labels, waiters)} "
            f"{verb(waiters, 'waiting', 'waiting')} "
            f"to get from {q.name}, but every thread that ever put to it "
            f"({name_all(labels, senders)}) has ended. Unless a thread that "
            "has not touched it yet puts something, this get waits forever."
        )
        key = ("get_stranded", q.id, tuple(waiters))
        return [(key, "lost_signal", text, True)]

    def _sync_wait(
        self, red: Any, s: Any, timed: set[str], labels: Labels
    ) -> list[Found]:
        waiters = _untimed(s.waiters, timed)
        senders = self._stranded(red, s.id)
        if not waiters or senders is None or (s.kind == "event" and s.is_set):
            return []
        method, third = _SENDS[s.kind]
        text = (
            f"The run ended with {name_all(labels, waiters)} waiting "
            f"on {s.name}, but every thread that ever {third} it "
            f"({name_all(labels, senders)}) has ended. Unless a thread that "
            f"has not touched it yet calls {method}(), this wait is never "
            "woken."
        )
        key = ("wait_stranded", s.id, tuple(waiters))
        return [(key, "lost_signal", text, True)]

    def _join(self, red: Any, q: Any, labels: Labels) -> list[Found]:
        if not q.joiners or q.items or q.unfinished < 1:
            return []
        if any(
            th.holding for th in red.threads.values() if th.status not in ENDED
        ):
            return []
        joiners = list(dict.fromkeys(q.joiners))
        text = (
            f"The run ended with {name_all(labels, joiners)} waiting "
            f"in join() for {q.unfinished} unfinished item(s) of {q.name}, "
            "but none is queued and no running thread holds one. A worker "
            "took the items and ended without calling task_done(), so "
            "join() cannot return."
        )
        key = ("join_stuck", q.id, q.unfinished)
        return [(key, "join_stuck", text, False)]
