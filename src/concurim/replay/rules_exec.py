"""Explanation rules for executor and asyncio task events.

Each rule returns ``(title, text, tone)``. ``n.q`` is the executor's name.
"""

from __future__ import annotations


def _size(count: int) -> str:
    """``count`` bytes as a short human-readable size."""
    return f"{count} bytes" if count < 1000 else f"{count / 1000:.1f} kB"


def copy_note(meta: dict) -> str:
    """Sentence on which arguments are copied and which are shared.

    Empty unless the work crosses a process boundary (the recorder adds
    ``copied_args``/``shared_args`` only there).
    """
    parts = []
    if meta.get("copied_args"):
        parts.append(
            f"{meta['copied_args']} argument(s) are copied into the worker "
            f"(about {_size(meta.get('copied_bytes', 0))} pickled), so changes "
            "it makes to them stay in the worker."
        )
    if meta.get("shared_args"):
        parts.append(
            f"{meta.get('shared_types')} is shared, so both processes see "
            "the same object."
        )
    return " ".join(parts)


def _created(n, ev, f):
    workers = ev.metadata.get("max_workers")
    return (
        "Executor created",
        f"{n.q} was created with up to {workers} worker(s). Tasks "
        "wait in its queue until a worker is free.",
        "info",
    )


def _submit(n, ev, f):
    return (
        "Task submitted",
        f"{n.t} submitted {n.o} to {n.q}. "
        f"{f.get('position')} task(s) pending, {f.get('running')} running. "
        f"{copy_note(ev.metadata)}".rstrip(),
        "info",
    )


def _started(n, ev, f):
    return (
        "Task started",
        f"{n.t} picked up {n.o} from {n.q} and began running it. "
        f"{f.get('pending')} still pending.",
        "ok",
    )


def _finished(n, ev, f):
    return (
        "Task finished",
        f"{n.t} finished {n.o}. {f.get('running')} running, "
        f"{f.get('pending')} pending."
        + (
            f" Its result (about {_size(ev.metadata['result_bytes'])}) is "
            "copied back to the caller."
            if ev.metadata.get("result_bytes")
            else ""
        ),
        "ok",
    )


def _failed(n, ev, f):
    return (
        "Task failed",
        f"{n.o} raised {ev.metadata.get('error')} in {n.t}. The exception "
        "is stored in its Future and re-raised by result().",
        "error",
    )


def _shutdown(n, ev, f):
    if f.get("dropped") or ev.metadata.get("cancel_futures"):
        text = (
            f"{n.t} shut down {n.q} and cancelled {f.get('dropped')} "
            "pending task(s). Running tasks finish."
        )
    else:
        text = (
            f"{n.t} shut down {n.q}. Pending tasks still run; no new "
            "submissions are accepted."
        )
    return ("Executor shut down", text, "warn")


def _task_cancelled_future(n, ev, f):
    return (
        "Task cancelled",
        f"{n.t} cancelled {n.o} with Future.cancel() before any worker "
        f"started it, so it will never run. {f.get('pending')} still "
        "pending.",
        "warn",
    )


def _callback(n, ev, f):
    return (
        "Callback ran",
        f"The done-callback {ev.metadata.get('callback')}() for {n.o} ran "
        f"on {n.t} ({ev.metadata.get('outcome')}). A callback runs on the "
        "thread that completes the future, usually a pool worker, not on "
        "the thread that registered it.",
        "info",
    )


def _collected(n, ev, f):
    return (
        "Result collected",
        f"{n.t} received {n.o} from as_completed() as number "
        f"{ev.metadata.get('order')}. as_completed yields tasks in the "
        "order they finish, not the order they were submitted.",
        "info",
    )


def _task_created(n, ev, f):
    return (
        "Task created",
        f"{n.t} created asyncio task “{ev.metadata.get('name')}”. It runs "
        "only when the event loop schedules it.",
        "info",
    )


def _step_started(n, ev, f):
    return (
        "Task running",
        f"The event loop resumed {n.t}. No other task runs until it "
        "awaits again.",
        "info",
    )


def _step_ended(n, ev, f):
    if ev.metadata.get("done"):
        return ("Task step ended", f"{n.t} ran to its end.", "info")
    return (
        "Task suspended",
        f"{n.t} awaited something and gave control back to the event loop.",
        "info",
    )


def _task_finished(n, ev, f):
    return ("Task finished", f"{n.t} completed.", "ok")


def _task_failed(n, ev, f):
    return (
        "Task failed",
        f"{n.t} ended with an unhandled {ev.metadata.get('error')}.",
        "error",
    )


def _task_cancelled(n, ev, f):
    return (
        "Task cancelled",
        f"{n.t} was cancelled: CancelledError was raised at its current await.",
        "warn",
    )
