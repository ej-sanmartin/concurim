"""Explanation rules for queue events.

Each rule returns ``(title, text, tone)``.
"""

from __future__ import annotations


def _cap(maxsize: int) -> str:
    return str(maxsize) if maxsize > 0 else "unbounded"


def _created(n, ev, f):
    cap = ev.metadata.get("maxsize", 0)
    what = f"capacity {cap}" if cap else "unbounded capacity"
    return ("Queue created", f"{n.q} was created with {what}.", "info")


def _put_started(n, ev, f):
    return (
        "Put attempted",
        f"{n.t} is putting {n.o} on {n.q} "
        f"({f.get('size')}/{_cap(f.get('maxsize', 0))} occupied).",
        "info",
    )


def _put_blocked(n, ev, f):
    return (
        "Put blocked",
        f"{n.t} tried to put {n.o} on {n.q}, but the queue "
        f"was full ({f.get('size')}/{f.get('maxsize')}). The operation "
        "stays blocked until a consumer removes an item.",
        "wait",
    )


def _put_completed(n, ev, f):
    waited = " after having been blocked" if f.get("was_blocked") else ""
    return (
        "Item enqueued",
        f"{n.t} put {n.o} into {n.q}{waited}. It is now "
        f"at position {f.get('position')} of "
        f"{_cap(f.get('maxsize', 0))}.",
        "ok",
    )


def _put_timeout(n, ev, f):
    return (
        "Put timed out",
        f"{n.t} waited {ev.metadata.get('timeout')}s to "
        f"put {n.o} on {n.q}, but it stayed full. queue.Full was raised "
        "and the item was not enqueued.",
        "error",
    )


def _put_failed(n, ev, f):
    why = {
        "full": "the queue was full and the call was non-blocking, so "
        "queue.Full was raised",
        "shutdown": "the queue has been shut down, so queue.ShutDown was "
        "raised",
    }.get(ev.metadata.get("reason"), f"it failed ({ev.metadata.get('reason')})")
    return (
        "Put failed",
        f"{n.t} could not put {n.o} on {n.q}: {why}.",
        "error",
    )


def _get_started(n, ev, f):
    return ("Get attempted", f"{n.t} is asking {n.q} for an item.", "info")


def _get_blocked(n, ev, f):
    return (
        "Get blocked",
        f"{n.t} tried to get an item from {n.q}, but it was "
        "empty. This thread waits for a producer (or a shutdown); other "
        "threads keep running.",
        "wait",
    )


def _get_completed(n, ev, f):
    waited = " after waiting" if f.get("was_blocked") else ""
    return (
        "Item dequeued",
        f"{n.t} removed {n.o} from the front of {n.q}"
        f"{waited}. It no longer occupies the queue "
        f"({f.get('size')}/{_cap(f.get('maxsize', 0))}) but stays "
        f"unfinished until task_done() is called "
        f"({f.get('unfinished')} unfinished).",
        "ok",
    )


def _get_timeout(n, ev, f):
    return (
        "Get timed out",
        f"{n.t} waited {ev.metadata.get('timeout')}s for "
        f"an item from {n.q}, but it stayed empty. queue.Empty was "
        "raised.",
        "error",
    )


def _get_failed(n, ev, f):
    why = {
        "empty": "the queue was empty and the call was non-blocking, so "
        "queue.Empty was raised",
        "shutdown": "the queue was shut down and drained, so queue.ShutDown "
        "was raised",
    }.get(ev.metadata.get("reason"), f"it failed ({ev.metadata.get('reason')})")
    return ("Get failed", f"{n.t} could not get from {n.q}: {why}.", "error")


def _task_done(n, ev, f):
    before, after = f.get("unfinished_before"), f.get("unfinished")
    explicit = (
        f" for {n.o}"
        if ev.object_id
        else " (it does not say which item finished)"
    )
    return (
        "task_done()",
        f"{n.t} called task_done() on {n.q}{explicit}. "
        f"Unfinished tasks: {before} → {after}.",
        "ok",
    )


def _task_done_failed(n, ev, f):
    return (
        "task_done() failed",
        f"{n.t} called task_done() on {n.q} more "
        "times than items were put, so ValueError was raised.",
        "error",
    )


def _join_started(n, ev, f):
    if f.get("unfinished"):
        return (
            "join() waiting",
            f"{n.t} called join() on {n.q}. It waits "
            f"until all {f['unfinished']} unfinished task(s) are marked "
            "done.",
            "wait",
        )
    return (
        "join() returns",
        f"{n.t} called join() on {n.q}; nothing was "
        "unfinished, so it returns immediately.",
        "info",
    )


def _join_completed(n, ev, f):
    return (
        "join() completed",
        f"join() returned in {n.t}: every item put on "
        f"{n.q} has been marked done (or discarded by shutdown).",
        "ok",
    )


def _join_failed(n, ev, f):
    return (
        "join() failed",
        f"join() in {n.t} raised {ev.metadata.get('error')}.",
        "error",
    )


def _shutdown(n, ev, f):
    if ev.metadata.get("immediate"):
        text = (
            f"{n.t} shut down {n.q} immediately. Queued items are "
            "discarded and blocked threads are woken with ShutDown."
        )
    else:
        text = (
            f"{n.t} shut down {n.q}. New puts raise ShutDown; consumers "
            f"can still drain the {f.get('size')} queued item(s) before "
            "get() raises ShutDown."
        )
    return ("Queue shut down", text, "warn")


def _discarded(n, ev, f):
    return (
        "Item discarded",
        f"{n.o} was removed from {n.q} by the immediate "
        f"shutdown without being consumed ({f.get('unfinished')} "
        "unfinished).",
        "warn",
    )
