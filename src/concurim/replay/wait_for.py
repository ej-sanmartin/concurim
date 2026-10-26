"""Wait-for cycles among locks and semaphores.

An edge means one actor cannot proceed until another releases a lock or a
semaphore permit. A cycle is observed blocking in this run. It is not a
statement about other schedules, and it is not drawn for queues or events:
those waits do not name who has to move next.
"""

from __future__ import annotations

from typing import Any

_KINDS = ("lock", "rlock", "semaphore")


def _labels(red: Any) -> dict[str, str]:
    """Display name per actor. Duplicate names keep the id."""
    counts: dict[str, int] = {}
    for thread in red.threads.values():
        counts[thread.name] = counts.get(thread.name, 0) + 1
    labels: dict[str, str] = {}
    for thread in red.threads.values():
        if counts[thread.name] == 1:
            labels[thread.id] = thread.name
        else:
            labels[thread.id] = f"{thread.name} ({thread.id})"
    return labels


def _edges(red: Any) -> list[tuple[str, str]]:
    """``(waiter, holder)`` pairs for locks and semaphores."""
    edges: list[tuple[str, str]] = []
    for sync in red.syncs.values():
        if sync.kind not in _KINDS:
            continue
        holders = list(dict.fromkeys(sync.holders))
        if not holders:
            continue
        seen: set[str] = set()
        for waiter_row in sync.waiters:
            waiter = waiter_row.get("thread")
            if not waiter or waiter in seen:
                continue
            seen.add(waiter)
            others = [holder for holder in holders if holder != waiter]
            # No one else can release it: the waiter is stuck on itself.
            targets = others or ([waiter] if waiter in holders else [])
            for holder in targets:
                edges.append((waiter, holder))
    return edges


def _cycles(edges: list[tuple[str, str]]) -> list[list[str]]:
    """Unique elementary cycles, each rotated to a stable start."""
    graph: dict[str, set[str]] = {}
    for waiter, holder in edges:
        graph.setdefault(waiter, set()).add(holder)
    found: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    def canonical(nodes: list[str]) -> tuple[str, ...]:
        if len(nodes) == 1:
            return (nodes[0],)
        rotations: list[tuple[str, ...]] = []
        reverse = list(reversed(nodes))
        for seq in (nodes, reverse):
            for i in range(len(seq)):
                rotations.append(tuple(seq[i:] + seq[:i]))
        return min(rotations)

    def walk(start: str, node: str, path: list[str]) -> None:
        for nxt in graph.get(node, ()):
            if nxt == start:
                sig = canonical(path)
                if sig not in seen:
                    seen.add(sig)
                    found.append(list(sig))
            elif nxt not in path:
                walk(start, nxt, path + [nxt])

    for node in sorted(graph):
        walk(node, node, [node])
    found.sort()
    return found


def _phrase(cycles: list[list[str]]) -> str:
    """One sentence naming the actors in each cycle."""
    parts: list[str] = []
    for cycle in cycles:
        if len(cycle) == 1:
            parts.append(f"{cycle[0]} is waiting for a lock it already holds")
            continue
        if len(cycle) == 2:
            names = f"{cycle[0]} and {cycle[1]}"
        else:
            names = ", ".join(cycle[:-1]) + f", and {cycle[-1]}"
        parts.append(f"{names} are waiting on locks one another holds")
    return ". ".join(parts) + "."


def waiting(red: Any) -> list[dict[str, Any]]:
    """Actors blocked on a lock or semaphore, and who holds it."""
    labels = _labels(red)
    rows: list[dict[str, Any]] = []
    for sync in red.syncs.values():
        if sync.kind not in _KINDS:
            continue
        holders = list(dict.fromkeys(sync.holders))
        seen: set[str] = set()
        for waiter_row in sync.waiters:
            waiter = waiter_row.get("thread")
            if not waiter or waiter in seen:
                continue
            seen.add(waiter)
            rows.append(
                {
                    "actor": labels.get(waiter, waiter),
                    "resource": sync.name,
                    "holders": [labels.get(h, h) for h in holders],
                }
            )
    rows.sort(key=lambda row: (row["actor"], row["resource"]))
    return rows


class WaitTracker:
    """Remember when a wait-for cycle appears and when it clears."""

    def __init__(self) -> None:
        self.episodes: list[dict[str, Any]] = []
        self._sig: tuple[tuple[str, ...], ...] = ()

    def observe(self, red: Any, index: int) -> str | None:
        """Note the cycle at event ``index``.

        Returns:
            A sentence when a cycle newly appears, else ``None``.
        """
        labels = _labels(red)
        cycles = _cycles(_edges(red))
        sig = tuple(tuple(c) for c in cycles)
        if sig == self._sig:
            return None
        if self._sig and self.episodes:
            self.episodes[-1]["resolved_at"] = index
        self._sig = sig
        if not sig:
            return None
        named = [[labels.get(a, a) for a in cycle] for cycle in cycles]
        self.episodes.append(
            {"at": index, "resolved_at": None, "actors": named}
        )
        return _phrase(named)

    def report(self, red: Any) -> dict[str, Any]:
        """The final wait-for picture: open cycles, history, waiters."""
        open_cycles: list[list[str]] = []
        if self.episodes and self.episodes[-1]["resolved_at"] is None:
            open_cycles = self.episodes[-1]["actors"]
        return {
            "waiting": waiting(red),
            "cycles": open_cycles,
            "episodes": [
                {
                    "at": ep["at"],
                    "resolved_at": ep["resolved_at"],
                    "actors": ep["actors"],
                }
                for ep in self.episodes
            ],
        }


def wait_warnings(program: dict[str, Any], report: dict[str, Any]) -> list[str]:
    """Warnings for an interrupted run and for cycles this picture contains."""
    notes: list[str] = []
    outcome = program.get("outcome")
    if outcome == "interrupted":
        text = (
            "Recording stopped before the program finished. "
            "The picture ends at the last observed event."
        )
        if program.get("still_blocked"):
            text += " Other threads were still running."
        notes.append(text)
    elif outcome == "running":
        notes.append(
            "This is a snapshot of a run that was still going. "
            "Events after this moment are not in the picture."
        )
    for episode in report.get("episodes", []):
        sentence = _phrase(episode["actors"])
        at = episode["at"] + 1
        resolved = episode["resolved_at"]
        if resolved is None:
            notes.append(
                f"At event {at}, {sentence} "
                "That was still true at the end of this picture."
            )
        else:
            notes.append(
                f"At event {at}, {sentence} "
                f"That had cleared by event {resolved + 1}."
            )
    return notes
