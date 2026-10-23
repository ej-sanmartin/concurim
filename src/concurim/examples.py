"""Locate the bundled example programs."""

from __future__ import annotations

from pathlib import Path


def example_path(name: str) -> Path:
    """Path of a bundled example (wheel layout, else a source checkout)."""
    package = Path(__file__).resolve().parent
    for base in (package / "_examples", package.parents[1] / "examples"):
        candidate = base / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"bundled example not found: {name}")
