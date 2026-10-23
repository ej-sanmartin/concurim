"""Find Python interpreters a program could be recorded with.

Discovery never executes anything: versions come from ``pyvenv.cfg`` or
from this process. Whether a user-chosen interpreter is usable is checked
when the (confirmed) run starts.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import sys
from pathlib import Path
from typing import Any

MIN_VERSION = (3, 13)


def _venv_python(venv: Path) -> Path:
    sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return venv / sub


def _venv_version(python: Path) -> str | None:
    cfg = python.parent.parent / "pyvenv.cfg"
    try:
        text = cfg.read_text("utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"^version(?:_info)?\s*=\s*([\d.]+)", text, re.M)
    return match.group(1) if match else None


def _supported(version: str | None) -> bool | None:
    """True/False when the version is known, ``None`` when it is not."""
    if version is None:
        return None
    parts = tuple(int(p) for p in version.split(".")[:2] if p.isdigit())
    return parts >= MIN_VERSION


def discover(project_dir: Path) -> list[dict[str, Any]]:
    """Candidate interpreters, most relevant first, without duplicates.

    Args:
        project_dir: Directory Concurim was launched from.

    Returns:
        Dicts with ``path``, ``label``, ``version`` (or ``None``) and
        ``supported`` (``True``/``False``/``None`` if unknown).
    """
    found: list[tuple[Path, str, str | None]] = []
    active = os.environ.get("VIRTUAL_ENV")
    if active:
        py = _venv_python(Path(active))
        found.append((py, "Active virtual environment", _venv_version(py)))
    local = _venv_python(project_dir / ".venv")
    found.append((local, "Project .venv", _venv_version(local)))
    found.append(
        (
            Path(sys.executable),
            "Python running Concurim",
            platform.python_version(),
        )
    )
    on_path = shutil.which("python3")
    if on_path:
        found.append((Path(on_path), "python3 on PATH", None))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path, label, version in found:
        key = os.path.abspath(path)
        if key in seen or not os.path.isfile(key):
            continue
        seen.add(key)
        out.append(
            {
                "path": key,
                "label": label,
                "version": version,
                "supported": _supported(version),
            }
        )
    return out
