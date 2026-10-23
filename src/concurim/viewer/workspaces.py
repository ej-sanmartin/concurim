"""Scratch copies of files dropped into the viewer.

A browser cannot reveal a dropped file's real location, so dropped files
are copied into a private temporary directory. Paths are validated so a
crafted name can never write outside that directory.
"""

from __future__ import annotations

import base64
import binascii
import secrets
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

MAX_FILES = 2000
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
ENTRY_NAMES = ("__main__.py", "main.py", "app.py", "run.py")


class WorkspaceError(ValueError):
    """The upload was rejected (bad path, too large, malformed)."""


def safe_relative(name: object) -> PurePosixPath:
    """Validate an uploaded relative path.

    Raises:
        WorkspaceError: If it is empty, absolute, has ``..`` or odd chars.
    """
    if not isinstance(name, str) or not name or len(name) > 400:
        raise WorkspaceError("invalid file path")
    path = PurePosixPath(name.replace("\\", "/"))
    bad = path.is_absolute() or any(
        p in ("", ".", "..") or ":" in p or "\x00" in p for p in path.parts
    )
    if bad:
        raise WorkspaceError(f"unsafe file path: {name!r}")
    return path


class Workspaces:
    """Creates and finds scratch workspaces under one private temp dir."""

    def __init__(self) -> None:
        self._root: Path | None = None
        self._known: set[str] = set()

    @property
    def root(self) -> Path:
        """The private scratch directory (created on first use, mode 0700)."""
        if self._root is None:
            self._root = Path(tempfile.mkdtemp(prefix="concurim-")).resolve()
        return self._root

    def create(self, files: object) -> dict[str, Any]:
        """Store uploaded files and describe the resulting workspace.

        Args:
            files: A list of ``{"path": str, "data": base64 str}``.

        Returns:
            ``{id, python_files, entries, suggested, file_count}``.
        """
        if not isinstance(files, list) or not files:
            raise WorkspaceError("no files")
        if len(files) > MAX_FILES:
            raise WorkspaceError(f"more than {MAX_FILES} files")
        ws_id = secrets.token_hex(8)
        base = self.root / "ws" / ws_id
        base.mkdir(parents=True)
        total = 0
        pyfiles: dict[str, str] = {}
        try:
            for item in files:
                if not isinstance(item, dict):
                    raise WorkspaceError("malformed file entry")
                rel = safe_relative(item.get("path"))
                try:
                    data = base64.b64decode(item.get("data", ""), validate=True)
                except (binascii.Error, TypeError, ValueError) as exc:
                    raise WorkspaceError("invalid file data") from exc
                total += len(data)
                if len(data) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                    raise WorkspaceError("upload too large")
                target = (base / rel).resolve()
                if base.resolve() not in target.parents:
                    raise WorkspaceError(f"unsafe file path: {rel}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                if target.suffix == ".py":
                    pyfiles[str(rel)] = data.decode("utf-8", "replace")
        except BaseException:
            shutil.rmtree(base, ignore_errors=True)
            raise
        if not pyfiles:
            shutil.rmtree(base, ignore_errors=True)
            raise WorkspaceError("no .py file in the upload")
        self._known.add(ws_id)
        entries = sorted(
            (p for p, text in pyfiles.items() if "__main__" in text),
            key=lambda p: (p.count("/"), p),
        )
        return {
            "id": ws_id,
            "file_count": len(files),
            "python_files": sorted(pyfiles),
            "entries": entries,
            "suggested": _suggest(entries, sorted(pyfiles)),
        }

    def resolve(self, ws_id: object, entry: object) -> tuple[Path, Path]:
        """Return ``(workspace_dir, script_path)`` for a known workspace.

        Raises:
            WorkspaceError: For unknown workspaces or entries outside it.
        """
        if not isinstance(ws_id, str) or ws_id not in self._known:
            raise WorkspaceError("unknown workspace")
        base = (self.root / "ws" / ws_id).resolve()
        script = (base / safe_relative(entry)).resolve()
        if base not in script.parents or script.suffix != ".py":
            raise WorkspaceError("entry point must be a .py file in the upload")
        if not script.is_file():
            raise WorkspaceError("entry point not found")
        return base, script

    def cleanup(self) -> None:
        """Delete every scratch file."""
        if self._root is not None:
            shutil.rmtree(self._root, ignore_errors=True)
            self._root = None
            self._known.clear()


def _suggest(entries: list[str], all_py: list[str]) -> str:
    for name in ENTRY_NAMES:
        for path in entries or all_py:
            if path == name or path.endswith("/" + name):
                return path
    return (entries or all_py)[0]
