"""Bundled sample programs and their pre-recorded traces.

Every ``.concurim`` file here is a real recording of the neighbouring
``.py`` file, produced by ``scripts/make_samples.py``. Nothing is
hand-written or synthetic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SAMPLES_DIR = Path(__file__).resolve().parent


def load_manifest() -> dict[str, Any]:
    """The gallery description (``samples`` and ``planned`` lists)."""
    return json.loads((SAMPLES_DIR / "manifest.json").read_text("utf-8"))


def find_sample(sample_id: str) -> dict[str, Any] | None:
    """Manifest entry for ``sample_id``, or ``None`` if there is none."""
    for entry in load_manifest()["samples"]:
        if entry["id"] == sample_id:
            return entry
    return None


def sample_file(name: str) -> Path:
    """Path of a file named in the manifest (never user-controlled)."""
    return SAMPLES_DIR / name
