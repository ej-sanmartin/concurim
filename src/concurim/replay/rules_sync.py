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
    elif ev.metadata.get("kind") == "rlock":
        text = (
            f"{n.q} was created. It is reentrant: the thread that holds it "
            "may acquire it again, and must release it once per acquire."
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
    if f.get("self_held") and f.get("kind") == "lock":
        return (
            "Acquire blocked on itself",
            f"{n.t} tried to acquire {n.q}, which it already holds. A plain "
            "Lock cannot be re-entered, so it is now waiting for itself. "
            "An RLock would let it through.",
            "error",
        )
    if _noun(ev) == "semaphore":
        why = "no permits were available"
    else:
        why = "it was already held"
    # Another process's events can arrive after this one, so the holder
    # may be unknown here even though the call did find the lock taken.
    count = f"{len(holders)} holder(s)" if holders else "holder not seen yet"
    return (
        "Acquire blocked",
        f"{n.t} tried to acquire {n.q}, but {why} ({count}). It waits; "
        "other threads keep running.",
        "wait",
    )


def _completed(n, ev, f):
    waited = " after waiting" if f.get("was_blocked") else ""
    if f.get("reentered"):
        return (
            "Re-entered",
            f"{n.t} already held {n.q} and acquired it again, so it is held "
            f"{f.get('depth')} deep. Other threads wait until it has been "
            f"released {f.get('depth')} times.",
            "ok",
        )
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
    elif f.get("kind") == "rlock" and f.get("depth"):
        text = (
            f"{n.t} released one level of {n.q}; it still holds it "
            f"{f['depth']} deep, so other threads keep waiting."
        )
    else:
        text = f"{n.t} released {n.q}."
        if f.get("remaining"):
            text += f" It is still held {f['remaining']} time(s)."
    return ("Released", text + extra, "ok")


def _release_failed(n, ev, f):
    why = {
        "not_locked": "it was not locked",
        "not_acquired": "no thread held it",
        "not_owner": "another thread holds it, and only the owner of a "
        "reentrant lock can release it",
    }.get(f.get("reason"), "it could not be released")
    return (
        "Release refused",
        f"{n.t} tried to release {n.q}, but {why}. release() raised "
        "RuntimeError.",
        "error",
    )
