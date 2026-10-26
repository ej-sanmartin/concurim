"""Export a recording as a video, GIF or PNG sequence.

The real viewer is rendered in a headless browser in *capture mode* (see
``frontend/src/capture.ts``). The exporter picks an event, waits until the
page shows exactly that state, takes a screenshot, and moves on, so no
clock or timer decides what a frame looks like. Frames go to ffmpeg, or to
PNG files. Exporting only loads a trace; it never runs the program.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from concurim.export.cdp import Browser, ExportError, find_browser
from concurim.recorder.serialization import load_trace

VIEWS = ("animation", "code", "timeline", "resources")
OVERLAYS = ("explanation", "timeline")
FORMATS = {".mp4", ".webm", ".gif"}
_READY_TIMEOUT_S = 20.0


@dataclass(frozen=True)
class ExportOptions:
    """What to render. Event numbers are 1-based, like the viewer's box."""

    view: str = "animation"
    start: int = 1
    end: int | None = None
    width: int = 1280
    height: int = 720
    fps: int = 30
    hold: float = 1.2
    overlays: tuple[str, ...] = OVERLAYS
    footer: bool = True
    theme: str = "dark"


def find_ffmpeg() -> str:
    """Path of ffmpeg: on ``PATH`` first, else the ``concurim[video]`` one."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # ty: ignore[unresolved-import]  # optional extra

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise ExportError(
            "ffmpeg not found. Install ffmpeg, or run "
            "`pip install 'concurim[video]'` for a bundled copy. "
            "(A directory output needs neither: it writes PNG frames.)"
        ) from None


def _encoder_args(suffix: str, fps: int) -> list[str]:
    """ffmpeg output arguments for one container format."""
    if suffix == ".gif":
        rate = min(fps, 15)
        graph = f"fps={rate},split[a][b];[a]palettegen[p];[b][p]paletteuse"
        return ["-vf", graph]
    pad = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    common = ["-vf", f"fps={fps},{pad}", "-pix_fmt", "yuv420p"]
    if suffix == ".webm":
        return [*common, "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0"]
    return [
        *common,
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-movflags",
        "+faststart",
    ]


class _FrameSink:
    """Where screenshots go: an ffmpeg process or numbered PNG files."""

    def __init__(self, output: Path, options: ExportOptions) -> None:
        self._dir: Path | None = None
        self._count = 0
        self._proc: subprocess.Popen[bytes] | None = None
        self._log = tempfile.TemporaryFile()  # noqa: SIM115 - closed below
        if output.suffix.lower() in FORMATS:
            command = [
                find_ffmpeg(),
                "-y",
                "-loglevel",
                "error",
                "-f",
                "image2pipe",
                "-c:v",
                "png",
                "-framerate",
                f"{1 / options.hold:.6f}",
                "-i",
                "-",
                "-fflags",
                "+bitexact",
                "-map_metadata",
                "-1",
                *_encoder_args(output.suffix.lower(), options.fps),
                str(output),
            ]
            self._proc = subprocess.Popen(  # noqa: S603 - fixed argv
                command, stdin=subprocess.PIPE, stderr=self._log
            )
        elif output.suffix == "":
            output.mkdir(parents=True, exist_ok=True)
            self._dir = output
        else:
            raise ExportError(
                f"unsupported output {output.suffix!r}: use .mp4, .webm, "
                ".gif, or a directory name for a PNG sequence"
            )

    def write(self, png: bytes) -> None:
        """Add one frame."""
        self._count += 1
        if self._dir is not None:
            (self._dir / f"frame-{self._count:05d}.png").write_bytes(png)
        elif self._proc and self._proc.stdin:
            try:
                self._proc.stdin.write(png)
            except BrokenPipeError:
                raise ExportError(self._failure()) from None

    def _failure(self) -> str:
        self._log.seek(0)
        text = self._log.read().decode(errors="replace").strip()
        return f"ffmpeg failed: {text or 'unknown error'}"

    def abort(self) -> None:
        """Stop ffmpeg after a failure so no half-written process lingers."""
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait()
        self._log.close()

    def close(self) -> None:
        """Finish the file; raise ``ExportError`` if ffmpeg failed."""
        try:
            if self._proc:
                if self._proc.stdin:
                    self._proc.stdin.close()
                if self._proc.wait() != 0:
                    raise ExportError(self._failure())
        finally:
            self._log.close()


def _footer(name: str, start: int, end: int, total: int, digest: str) -> str:
    """Burned-in provenance line: what was recorded, which events, hash."""
    return f"{name} · events {start}-{end} of {total} · sha256 {digest[:12]}"


def _wait_ready(browser: Browser) -> None:
    deadline = time.monotonic() + _READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if browser.evaluate("!!window.__concurim && window.__concurim.ready"):
            return
        time.sleep(0.1)
    raise ExportError("the viewer did not become ready for capture")


def export_video(
    trace_path: Path,
    output: Path,
    options: ExportOptions,
    log: Callable[[str], None] = lambda _msg: None,
) -> int:
    """Render ``trace_path`` to ``output``; return the frame count.

    The output kind follows the suffix (.mp4, .webm, .gif) or is a directory
    of PNG frames. Raises ``ExportError`` for fixable problems.
    """
    from concurim.viewer.server import ViewerServer

    if options.view not in VIEWS:
        raise ExportError(f"view must be one of {', '.join(VIEWS)}")
    trace = load_trace(trace_path)
    digest = hashlib.sha256(trace_path.read_bytes()).hexdigest()
    server = ViewerServer(trace, 0, label=trace_path.name)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sink = browser = None
    try:
        total = len(json.loads(server.session.replay_json or b"{}")["events"])
        start, end = options.start, options.end or total
        if not 1 <= start <= end <= total:
            raise ExportError(
                f"events must satisfy 1 <= start <= end <= {total}"
            )
        sink = _FrameSink(output, options)
        browser = Browser(find_browser(), options.width, options.height)
        browser.page(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": "localStorage.setItem("
                f"'concurim-theme','{options.theme}')"
            },
        )
        query = {
            "capture": "1",
            "view": options.view,
            "overlays": ",".join(options.overlays),
            "footer": _footer(trace_path.name, start, end, total, digest)
            if options.footer
            else "",
        }
        url = f"{server.url}?{urlencode(query)}"
        browser.page("Page.navigate", {"url": url})
        _wait_ready(browser)
        for n, index in enumerate(range(start - 1, end), 1):
            browser.evaluate(f"window.__concurim.seek({index})")
            sink.write(browser.screenshot())
            log(f"frame {n}/{end - start + 1}")
        sink.close()
        return end - start + 1
    except BaseException:
        if sink:
            sink.abort()
        raise
    finally:
        if browser:
            browser.close()
        server.shutdown()
        server.server_close()
