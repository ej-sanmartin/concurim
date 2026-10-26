"""Explanation rules for event and condition events.

Each rule returns ``(title, text, tone)``. ``n.q`` is the resource name.
The wording follows the semantics of the standard library: a notification
does not release the lock, a woken waiter must still re-acquire it, and the
order in which waiters wake is not something to rely on.
"""

from __future__ import annotations


def _event_created(n, ev, f):
    state = "already set" if ev.metadata.get("is_set") else "not set"
    return (
        "Event created",
        f"{n.q} was created ({state}). Threads that wait on it block "
        "until some thread sets it.",
        "info",
    )


def _event_set(n, ev, f):
    if f.get("already_set"):
        text = f"{n.t} set {n.q}, which was already set. Nothing changes."
    else:
        waiting = f.get("waiting") or 0
        text = f"{n.t} set {n.q}. "
        text += (
            f"{waiting} waiting thread(s) can now continue; setting does "
            "not make them run immediately."
            if waiting
            else "Later waits return at once until it is cleared."
        )
    return ("Event set", text, "ok")


def _event_cleared(n, ev, f):
    return (
        "Event cleared",
        f"{n.t} cleared {n.q}. Later waits block again.",
        "info",
    )


def _event_wait_started(n, ev, f):
    return ("Wait attempted", f"{n.t} is waiting for {n.q}.", "info")


def _event_wait_blocked(n, ev, f):
    return (
        "Wait blocked",
        f"{n.t} waits for {n.q}, which is not set. It stays blocked "
        "until another thread sets it"
        + (
            f" (timeout {ev.metadata.get('timeout')}s)."
            if ev.metadata.get("timeout") is not None
            else "."
        ),
        "wait",
    )


def _event_wait_completed(n, ev, f):
    after = " after waiting" if f.get("was_blocked") else " (already set)"
    return ("Wait finished", f"{n.t} saw {n.q} set{after}.", "ok")


def _event_wait_timeout(n, ev, f):
    return (
        "Wait timed out",
        f"{n.t} stopped waiting for {n.q} after "
        f"{ev.metadata.get('timeout')}s; it was still not set.",
        "error",
    )


def _wait_failed(n, ev, f):
    return (
        "Wait failed",
        f"{n.t} left its wait on {n.q} with "
        f"{ev.metadata.get('error') or 'an error'}.",
        "error",
    )


def _condition_created(n, ev, f):
    lock = ev.metadata.get("lock")
    tail = " Its lock is shown as a separate resource." if lock else ""
    return (
        "Condition created",
        f"{n.q} was created. Threads wait on it for a state change and "
        f"are woken by notify().{tail}",
        "info",
    )


def _cond_wait_started(n, ev, f):
    return (
        "Wait started",
        f"{n.t} released the lock of {n.q} and is waiting to be notified. "
        f"{f.get('waiting')} thread(s) waiting.",
        "wait",
    )


def _notify(n, ev, f):
    woken = f.get("woken") or 0
    if not woken:
        text = f"{n.t} notified {n.q}, but no thread was waiting."
    else:
        count = ev.metadata.get("n")
        scope = "everyone" if f.get("everyone") else f"up to {count}"
        text = (
            f"{n.t} notified {scope} of {f.get('waiting')} waiting "
            f"thread(s) on {n.q}: {woken} can wake. The notifier still "
            "holds the lock, so a woken thread first has to re-acquire it, "
            "and which one runs first is not guaranteed."
        )
    return ("Notify", text, "ok")


def _cond_wait_completed(n, ev, f):
    return (
        "Woken",
        f"{n.t} was notified on {n.q} and has re-acquired its lock, so it "
        "can continue. Its condition may no longer hold: check it again.",
        "ok",
    )


def _cond_wait_timeout(n, ev, f):
    return (
        "Wait timed out",
        f"{n.t} was not notified on {n.q} within "
        f"{ev.metadata.get('timeout')}s. It re-acquired the lock and "
        "continues.",
        "error",
    )


def _group_created(n, ev, f):
    return (
        "Task group created",
        f"{n.q} was created. Tasks started through it are awaited when its "
        "`async with` block ends; if one fails, the others are cancelled.",
        "info",
    )


def _group_task_added(n, ev, f):
    return (
        "Task added to group",
        f"{n.t} started task “{f.get('name')}” in {n.q}. It runs "
        f"concurrently; {f.get('running')} task(s) in the group are "
        "unfinished.",
        "info",
    )


def _group_exit_started(n, ev, f):
    if f.get("body_error"):
        why = (
            f" The block ended with {f['body_error']}, so the group cancels "
            "its remaining tasks."
        )
    else:
        why = ""
    if not f.get("running"):
        text = f"{n.t} reached the end of {n.q}: every task already finished."
        return ("Group block ended", text, "info")
    return (
        "Waiting for the group",
        f"{n.t} reached the end of the block of {n.q} and is suspended "
        f"until its {f.get('running')} unfinished task(s) end.{why}",
        "wait",
    )


def _group_exit_completed(n, ev, f):
    if f.get("error"):
        return (
            "Group failed",
            f"The block of {n.q} ended with {f['error']}. A failing task "
            "cancels its siblings and the errors are raised together.",
            "error",
        )
    return (
        "Group finished",
        f"All {f.get('members')} task(s) of {n.q} finished; {n.t} continues.",
        "ok",
    )
