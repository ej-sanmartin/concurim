"""Replay data for the code view: function bodies and sampled lines."""

from __future__ import annotations

import ast
from typing import Any

from concurim.recorder.events import Event
from concurim.recorder.events import EventType as E


def function_ranges(sources: dict[str, str]) -> dict[str, list[list[int]]]:
    """First and last line of every function in each embedded source file.

    The first line is the first decorator when there is one, matching the
    line Python reports for a function's start. Files that do not parse
    (the text comes from an untrusted trace) are skipped.

    Args:
        sources: Display path -> source text.

    Returns:
        Display path -> sorted ``[first, last]`` pairs.
    """
    out: dict[str, list[list[int]]] = {}
    for path, text in sources.items():
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            continue
        spans = [
            [
                min([n.lineno, *(d.lineno for d in n.decorator_list)]),
                n.end_lineno or n.lineno,
            ]
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        if spans:
            out[path] = sorted(spans)
    return out


def split_line_samples(
    events: list[Event],
) -> tuple[list[Event], list[dict[str, Any]]]:
    """Separate sampled positions from the events that change state.

    Samples would otherwise be played back as events of their own. Each one
    is placed after the last real event that precedes it (``at``).

    Returns:
        ``(events without samples, samples)`` where a sample is
        ``{at, actor, file, line, function}``.
    """
    kept: list[Event] = []
    samples: list[dict[str, Any]] = []
    for ev in events:
        if ev.event_type != E.CODE_SAMPLED:
            kept.append(ev)
        elif ev.source is not None and ev.actor:
            samples.append(
                {
                    "at": max(len(kept) - 1, 0),
                    "actor": ev.actor,
                    "file": ev.source.file,
                    "line": ev.source.line,
                    "function": ev.source.function,
                }
            )
    return kept, samples
