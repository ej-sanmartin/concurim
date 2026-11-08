"""What the recorded events say happened before what.

Each actor has a logical clock (a vector clock). It ticks on every event of
that actor and is joined with the sender's clock at every hand-off the
trace shows: a thread or task start, an item put then got, a task
submitted then started, an event set then waited on, a condition notified
then resumed, and a lock or semaphore released then acquired. An access is
*ordered before* another when the second actor's clock has reached the
first access's tick.

Not seen, so never assumed: ``Thread.join()`` (it leaves no event), a
barrier, and anything that happens outside the instrumented objects.
"""

from __future__ import annotations

from typing import Any

from concurim.recorder.events import Event
from concurim.recorder.events import EventType as E

Clock = dict[str, int]

# event type -> (kind of hand-off, which side of it)
_SEND, _TAKE = "send", "take"
_BY_RESOURCE = {
    E.LOCK_RELEASED: ("lock", _SEND),
    E.LOCK_ACQUIRE_COMPLETED: ("lock", _TAKE),
    E.SEMAPHORE_RELEASED: ("lock", _SEND),
    E.SEMAPHORE_ACQUIRE_COMPLETED: ("lock", _TAKE),
    E.EVENT_SET: ("event", _SEND),
    E.EVENT_WAIT_COMPLETED: ("event", _TAKE),
    E.CONDITION_NOTIFY: ("condition", _SEND),
    E.CONDITION_WAIT_COMPLETED: ("condition", _TAKE),
}
_BY_OBJECT = {
    E.QUEUE_PUT_COMPLETED: _SEND,
    E.QUEUE_GET_COMPLETED: _TAKE,
    E.EXECUTOR_SUBMIT: _SEND,
    E.EXECUTOR_TASK_STARTED: _TAKE,
}


def _join(into: Clock, other: Clock) -> None:
    """Raise every component of ``into`` to at least that of ``other``."""
    for actor, tick in other.items():
        if tick > into.get(actor, 0):
            into[actor] = tick


class Order:
    """Clocks per actor, updated by ``observe`` in event order."""

    def __init__(self) -> None:
        self._clocks: dict[str, Clock] = {}
        self._carried: dict[tuple[str, str], Clock] = {}
        self._spawned: dict[str, Clock] = {}  # by task id
        self._starting: dict[str, list[Clock]] = {}  # by thread name

    def observe(self, red: Any, ev: Event) -> None:
        """Advance the acting actor's clock and apply this event's edges."""
        actor = ev.actor
        if actor is None:
            return
        clock = self._clocks.setdefault(actor, {})
        self._inherit(red, ev, actor, clock)
        clock[actor] = clock.get(actor, 0) + 1
        t = ev.event_type
        if t == E.THREAD_START_REQUESTED:
            name = str(ev.metadata.get("child_name", ""))
            self._starting.setdefault(name, []).append(dict(clock))
        elif t == E.TASK_CREATED:
            child = str(ev.metadata.get("child", ""))
            if child:
                self._spawned[child] = dict(clock)
        self._handoff(ev, clock)

    def tick(self, actor: str) -> int:
        """The actor's own clock component, as of its latest event."""
        return self._clocks.get(actor, {}).get(actor, 0)

    def ordered(self, actor: str, tick: int, before: str) -> bool:
        """Whether ``actor``'s event number ``tick`` precedes ``before``'s now.

        Args:
            actor: Who made the earlier access.
            tick: ``tick(actor)`` taken at that access.
            before: The actor now accessing.
        """
        return tick <= self._clocks.get(before, {}).get(actor, 0)

    def _inherit(self, red: Any, ev: Event, actor: str, clock: Clock) -> None:
        """A new thread or task starts knowing what its parent knew."""
        if ev.event_type == E.THREAD_STARTED:
            th = red.threads.get(actor)
            queue = self._starting.get(th.name if th else "")
            if queue:
                _join(clock, queue.pop(0))
        elif actor in self._spawned:
            _join(clock, self._spawned.pop(actor))

    def _handoff(self, ev: Event, clock: Clock) -> None:
        """Send this actor's clock through, or take what was sent."""
        t = ev.event_type
        if t in _BY_RESOURCE and ev.resource_id:
            kind, side = _BY_RESOURCE[t]
            key = (kind, ev.resource_id)
        elif t in _BY_OBJECT and ev.object_id:
            kind, side = "object", _BY_OBJECT[t]
            key = (kind, ev.object_id)
        else:
            return
        if side == _SEND:
            _join(self._carried.setdefault(key, {}), clock)
        elif key in self._carried:
            _join(clock, self._carried[key])
