"""Explanation rules for tracked shared values (``cell.*`` events).

Each rule returns ``(title, text, tone)``. ``n.q`` is the cell's name.
"""

from __future__ import annotations


def _holding(f) -> str:
    names = f.get("lock_names") or []
    return f"holding {', '.join(names)}" if names else "holding no lock"


def _created(n, ev, f):
    return (
        "Shared value created",
        f"{n.q} is a tracked shared value. Every read and write is "
        "recorded with the locks the thread held at that moment.",
        "info",
    )


def _read(n, ev, f):
    value = f" and saw {f['preview']}" if f.get("preview") is not None else ""
    return (
        "Value read",
        f"{n.t} read {n.q}{value}, {_holding(f)}.",
        "info",
    )


def _write(n, ev, f):
    change = ""
    if f.get("preview") is not None:
        before = f.get("previous")
        change = (
            f", changing it from {before} to {f['preview']}"
            if before is not None
            else f", setting it to {f['preview']}"
        )
    return (
        "Value written",
        f"{n.t} wrote {n.q}{change}, {_holding(f)}.",
        "ok",
    )
