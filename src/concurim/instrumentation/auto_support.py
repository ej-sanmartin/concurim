"""Helpers for the automatic instrumentation classes.

They decide, from the creating frame, whether an object belongs to the
user's program (traced) or to the standard library or a package (left plain).
"""

from __future__ import annotations

import os
import sys

from concurim.recorder.collector import INTERNAL_FILES, mark_internal
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)

_STDLIB = os.path.dirname(os.__file__) + os.sep


def user_caller(depth: int) -> bool:
    """Whether the caller ``depth`` frames above the caller is user code."""
    try:
        name = sys._getframe(depth + 1).f_code.co_filename
    except ValueError:
        return False
    return not (
        name.startswith(("<frozen", _STDLIB))
        or "-packages" in name
        or name in INTERNAL_FILES
    )


def creation_name(label: str) -> str | None:
    """``"Queue (line 12)"``, from the line that created the object."""
    rec = active_recorder()
    source = rec.capture_source() if rec else None
    return f"{label} (line {source.line})" if source else None


def in_stdlib(depth: int) -> bool:
    """Whether the caller ``depth`` frames above the caller is stdlib code."""
    try:
        name = sys._getframe(depth + 1).f_code.co_filename
    except ValueError:
        return False
    return name.startswith(("<frozen", _STDLIB)) and "-packages" not in name
