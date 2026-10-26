"""Export jobs started from the web UI (one at a time).

The same exporter as ``concurim export``. The output location is chosen
here, never by the request: files live in a private temporary directory
and are removed when a new export starts or the server closes.
"""

from __future__ import annotations

import re
import secrets
import shutil
import tempfile
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from concurim.export.cdp import ExportError, find_browser
from concurim.export.options import (
    FORMATS,
    OVERLAYS,
    SIZES,
    THEMES,
    VIDEO_FORMATS,
    VIEWS,
    event_range,
    options_from_request,
)
from concurim.export.sink import find_ffmpeg
from concurim.export.video import export_video
from concurim.viewer.session import Session

CONTENT_TYPES = {
    "mp4": "video/mp4",
    "webm": "video/webm",
    "gif": "image/gif",
    "png": "application/zip",
}


class ExportConflict(Exception):
    """An export is already running."""


class ExportNotFound(Exception):
    """No export with that id (or it has nothing to download yet)."""


@dataclass
class _Job:
    id: str
    fmt: str
    folder: Path
    filename: str
    total: int = 0
    done: int = 0
    state: str = "running"  # running | done | failed | cancelled
    error: str | None = None
    stop: threading.Event = field(default_factory=threading.Event)


def capabilities() -> dict[str, Any]:
    """What this machine can export, and the choices the dialog offers."""
    problems: dict[str, str] = {}
    for key, probe in (("browser", find_browser), ("ffmpeg", find_ffmpeg)):
        try:
            probe()
        except ExportError as error:
            problems[key] = str(error)
    return {
        "browser": "browser" not in problems,
        "ffmpeg": "ffmpeg" not in problems,
        "problems": problems,
        "formats": list(FORMATS),
        "video_formats": list(VIDEO_FORMATS),
        "views": list(VIEWS),
        "overlays": list(OVERLAYS),
        "themes": list(THEMES),
        "sizes": list(SIZES),
    }


class ExportManager:
    """Runs an export of the session's trace on a background thread."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._lock = threading.Lock()
        self._job: _Job | None = None
        self._thread: threading.Thread | None = None

    def start(self, request: dict[str, Any]) -> dict[str, Any]:
        """Validate ``request`` and begin exporting; returns the status."""
        options, fmt = options_from_request(request)
        trace, label = self._session.trace, self._session.label
        if trace is None:
            raise ExportError("no recording is open")
        event_range(options, self._session.event_count)
        with self._lock:
            if self._job and self._job.state == "running":
                raise ExportConflict("an export is already running")
            self._discard()
            safe = re.sub(r"[^\w.-]+", "-", label or "trace", flags=re.ASCII)
            ext = "zip" if fmt == "png" else fmt
            folder = Path(tempfile.mkdtemp(prefix="concurim-export-"))
            job = _Job(
                id=secrets.token_hex(8),
                fmt=fmt,
                folder=folder,
                filename=f"{safe.strip('-')[:60] or 'trace'}.{ext}",
            )
            self._job = job
        output = folder / ("frames" if fmt == "png" else f"clip.{fmt}")

        def progress(done: int, total: int) -> None:
            job.done, job.total = done, total

        def work() -> None:
            try:
                export_video(
                    trace, label or "trace", output, options, progress,
                    job.stop.is_set,
                )  # fmt: skip
                if fmt == "png":
                    _zip_frames(output, folder / "clip.zip")
                job.state = "done"
            except ExportError as error:
                cancelled = job.stop.is_set()
                job.state = "cancelled" if cancelled else "failed"
                job.error = None if cancelled else str(error)
            except Exception as error:  # reported to the user
                job.state, job.error = "failed", f"export failed: {error}"

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        return self._status(job)

    def status(self, job_id: str) -> dict[str, Any]:
        """Progress of an export."""
        return self._status(self._get(job_id))

    def cancel(self, job_id: str) -> dict[str, Any]:
        """Ask a running export to stop at the next event."""
        job = self._get(job_id)
        job.stop.set()
        return self._status(job)

    def file(self, job_id: str) -> tuple[str, bytes, str]:
        """(download name, bytes, content type) of a finished export."""
        job = self._get(job_id)
        if job.state != "done":
            raise ExportNotFound("the export is not finished")
        name = "clip.zip" if job.fmt == "png" else f"clip.{job.fmt}"
        return (
            job.filename,
            (job.folder / name).read_bytes(),
            CONTENT_TYPES[job.fmt],
        )

    def shutdown(self) -> None:
        """Stop a running export and delete its files."""
        with self._lock:
            if self._job:
                self._job.stop.set()
            if self._thread:
                self._thread.join(timeout=10)
            self._discard()

    def _get(self, job_id: str) -> _Job:
        if self._job is None or self._job.id != job_id:
            raise ExportNotFound("no such export")
        return self._job

    def _discard(self) -> None:
        if self._job:
            shutil.rmtree(self._job.folder, ignore_errors=True)
            self._job = None

    @staticmethod
    def _status(job: _Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "state": job.state,
            "done": job.done,
            "total": job.total,
            "error": job.error,
            "filename": job.filename,
        }


def _zip_frames(frames: Path, target: Path) -> None:
    """Bundle PNG frames (already compressed) into one download."""
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as archive:
        for png in sorted(frames.glob("frame-*.png")):
            archive.write(png, png.name)
