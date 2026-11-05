"""Small helpers shared by the hazard detectors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

ENDED = ("finished", "failed", "cancelled")

# ``(dedupe key, kind, sentence, inferred)``
Found = tuple[tuple[Any, ...], str, str, bool]
Labels = Callable[[], dict[str, str]]


def join_names(names: list[str]) -> str:
    """``A``, ``A and B`` or ``A, B, and C``."""
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def name_all(labels: Labels, actors: list[str]) -> str:
    """Display names of ``actors`` as one phrase."""
    names = labels()
    return join_names([names.get(a, a) for a in actors])


def verb(actors: list[str], one: str, many: str) -> str:
    """``one`` for a single actor, else ``many`` (``waits``/``wait``)."""
    return one if len(actors) == 1 else many


def ended(red: Any, actor: str) -> bool:
    """Whether ``actor`` is known and has finished, failed or been cancelled."""
    th = red.threads.get(actor)
    return th is not None and th.status in ENDED
