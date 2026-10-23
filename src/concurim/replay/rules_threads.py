"""Explanation rules for thread, work and lineage events.

Each rule returns ``(title, text, tone)``.
"""

from __future__ import annotations


def _thread_registered(n, ev, f):
    return (
        "Thread seen",
        f"{n.t} performed its first instrumented "
        "operation, so it appears in the trace.",
        "info",
    )


def _start_requested(n, ev, f):
    child = ev.metadata.get("child_name", "a new thread")
    return (
        "Thread start requested",
        f"{n.t} called start() for thread “{child}”. The new thread may "
        "begin running at any later moment.",
        "info",
    )


def _thread_started(n, ev, f):
    return ("Thread started", f"{n.t} began running its target.", "info")


def _thread_finished(n, ev, f):
    extra = ""
    if f.get("left_holding"):
        extra = (
            f" It still held {f['left_holding']} received item(s) "
            "without a matching task_done()."
        )
    if f.get("left_locked"):
        extra += (
            f" It still held {', '.join(f['left_locked'])} "
            "when it ended, so that lock stays locked."
        )
    return ("Thread finished", f"{n.t} finished.{extra}", "ok")


def _thread_failed(n, ev, f):
    return (
        "Thread failed",
        f"{n.t} ended with an unhandled "
        f"{ev.metadata.get('error', 'exception')}.",
        "error",
    )


def _work_started(n, ev, f):
    on = f" on {n.o}" if ev.object_id else ""
    return (
        "Work started",
        f"{n.t} began “{ev.metadata.get('name')}”{on}. "
        "This span was marked explicitly in the program.",
        "info",
    )


def _work_finished(n, ev, f):
    return (
        "Work finished",
        f"{n.t} finished “{ev.metadata.get('name')}”.",
        "ok",
    )


def _work_failed(n, ev, f):
    return (
        "Work failed",
        f"“{ev.metadata.get('name')}” in {n.t} raised "
        f"{ev.metadata.get('error')}.",
        "error",
    )


def _derived(n, ev, f):
    parent = n.obj(ev.metadata.get("parent_object_id"))
    return (
        "Lineage recorded",
        f"{n.t} declared that {n.o} was derived from "
        f"{parent}. This link comes from an explicit annotation, not from "
        "comparing values.",
        "info",
    )
