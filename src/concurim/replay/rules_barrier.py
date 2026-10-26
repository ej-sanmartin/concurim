"""Explanation rules for barrier events.

Each rule returns ``(title, text, tone)``. ``n.q`` is the barrier's name.
The last arrival does not block; earlier ones do, until the party is
complete or the barrier is aborted, reset, or timed out.
"""

from __future__ import annotations


def _created(n, ev, f):
    parties = ev.metadata.get("parties")
    return (
        "Barrier created",
        f"{n.q} was created for {parties} arrivals. A thread or task "
        "that reaches it waits until that many have arrived, then they "
        "all continue.",
        "info",
    )


def _started(n, ev, f):
    return ("Arrival attempted", f"{n.t} reached {n.q}.", "info")


def _blocked(n, ev, f):
    arrived = int(ev.metadata.get("waiting") or 0) + 1
    parties = ev.metadata.get("parties")
    return (
        "Arrival waiting",
        f"{n.t} is waiting at {n.q}. {arrived} of {parties} have "
        "arrived; they stay blocked until the party is complete.",
        "wait",
    )


def _completed(n, ev, f):
    index = ev.metadata.get("index")
    if f.get("was_blocked"):
        text = (
            f"{n.t} was released from {n.q} with the others "
            f"(arrival index {index})."
        )
    else:
        text = (
            f"{n.t} was the arrival that released {n.q} "
            f"(arrival index {index})."
        )
    return ("Barrier released", text, "ok")


def _failed(n, ev, f):
    if ev.metadata.get("broken"):
        text = (
            f"{n.t} left {n.q} with BrokenBarrierError. Further waits "
            "fail until the barrier is reset."
        )
    else:
        text = (
            f"{n.t} left {n.q} with BrokenBarrierError because it was "
            "reset. A new party can start."
        )
    return ("Arrival failed", text, "error")


def _abort(n, ev, f):
    waiting = f.get("waiting", 0)
    return (
        "Barrier aborted",
        f"{n.t} aborted {n.q}. {waiting} waiting arrival(s) wake with "
        "BrokenBarrierError, and the barrier stays broken.",
        "error",
    )


def _reset(n, ev, f):
    waiting = f.get("waiting", 0)
    return (
        "Barrier reset",
        f"{n.t} reset {n.q}. {waiting} waiting arrival(s) wake with "
        "BrokenBarrierError, and a new party can start.",
        "warn",
    )
