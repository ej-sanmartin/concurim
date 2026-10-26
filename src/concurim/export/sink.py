"""Where exported frames go: an ffmpeg process or numbered PNG files."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from concurim.export.cdp import ExportError

VIDEO_SUFFIXES = {".mp4", ".webm", ".gif"}


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
    return [*common, "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-movflags", "+faststart"]  # fmt: skip


class FrameSink:
    """Takes PNG screenshots in order; ``repeat`` holds a frame on screen."""

    def __init__(self, output: Path, fps: int) -> None:
        self._dir: Path | None = None
        self._count = 0
        self._last_png: bytes | None = None
        self._last_path: Path | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._log = tempfile.TemporaryFile()  # noqa: SIM115 - closed below
        suffix = output.suffix.lower()
        if suffix in VIDEO_SUFFIXES:
            command = [
                find_ffmpeg(), "-y", "-loglevel", "error",
                "-f", "image2pipe", "-c:v", "png",
                "-framerate", str(fps), "-i", "-",
                "-fflags", "+bitexact", "-map_metadata", "-1",
                *_encoder_args(suffix, fps),
                str(output),
            ]  # fmt: skip
            self._proc = subprocess.Popen(  # noqa: S603 - fixed argv
                command, stdin=subprocess.PIPE, stderr=self._log
            )
        elif suffix == "":
            output.mkdir(parents=True, exist_ok=True)
            self._dir = output
        else:
            raise ExportError(
                f"unsupported output {output.suffix!r}: use .mp4, .webm, "
                ".gif, or a directory name for a PNG sequence"
            )

    def write(self, png: bytes, repeat: int = 1) -> None:
        """Add one frame, shown for ``repeat`` frames."""
        for _ in range(repeat):
            self._count += 1
            if self._dir is not None:
                self._write_file(png)
            elif self._proc and self._proc.stdin:
                try:
                    self._proc.stdin.write(png)
                except BrokenPipeError:
                    raise ExportError(self._failure()) from None

    def _write_file(self, png: bytes) -> None:
        """Numbered PNG; a held frame is a hard link to its first copy."""
        assert self._dir is not None
        path = self._dir / f"frame-{self._count:05d}.png"
        if self._last_png == png and self._last_path is not None:
            try:
                os.link(self._last_path, path)
                self._last_path = path
                return
            except OSError:
                pass
        path.write_bytes(png)
        self._last_png, self._last_path = png, path

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
