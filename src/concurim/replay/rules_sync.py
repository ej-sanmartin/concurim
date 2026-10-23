"""Explanation rules for lock and semaphore events.

Each rule returns ``(title, text, tone)``. ``n.q`` is the resource name.
"""

from __future__ import annotations


def _noun(ev) -> str:
    return "semaphore" if ev.event_type.startswith("semaphore") else "lock"


def _created(n, ev, f):
    if _noun(ev) == "semaphore":
        text = (
            f"{n.q} was created with {ev.metadata.get('value')} permit(s). "
            "An acquire takes one; a release gives one back."
        )
    else:
        text = f"{n.q} was created. Only one holder at a time may own it."
    return (f"{_noun(ev).title()} created", text, "info")


def _started(n, ev, f):
    return (
        "Acquire attempted",
        f"{n.t} is trying to acquire {n.q}.",
        "info",
    )


def _blocked(n, ev, f):
    holders = f.get("holders") or []
    if _noun(ev) == "semaphore":
        why = "no permits were available"
    else:
        why = "it was already held"
    return (
        "Acquire blocked",
        f"{n.t} tried to acquire {n.q}, but {why} "
        f"({len(holders)} holder(s)). It waits; other threads keep "
        "running.",
        "wait",
    )


def _completed(n, ev, f):
    waited = " after waiting" if f.get("was_blocked") else ""
    return (
        "Acquired",
        f"{n.t} acquired {n.q}{waited}.",
        "ok",
    )


def _failed(n, ev, f):
    why = {
        "nonblocking": "it was unavailable and the call was non-blocking",
        "timeout": f"it stayed unavailable for {ev.metadata.get('timeout')}s",
        "cancelled": "the waiting task was cancelled",
    }.get(ev.metadata.get("reason"), "the acquire failed")
    return (
        "Acquire failed",
        f"{n.t} did not acquire {n.q}: {why}.",
        "error",
    )


def _released(n, ev, f):
    extra = ""
    if f.get("released_by_other"):
        extra = " It was released by a different thread than the holder."
    if _noun(ev) == "semaphore":
        text = f"{n.t} released {n.q}; {f.get('value')} permit(s) available."
    else:
        text = f"{n.t} released {n.q}."
        if f.get("remaining"):
            text += f" It is still held {f['remaining']} time(s)."
    return ("Released", text + extra, "ok")
