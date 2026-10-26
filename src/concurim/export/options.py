"""What an export renders, and the checks shared by the CLI and the web UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from concurim.export.cdp import ExportError

VIEWS = ("animation", "code", "timeline", "resources")
OVERLAYS = ("explanation", "timeline")
THEMES = ("dark", "light")
VIDEO_FORMATS = ("mp4", "webm", "gif")
FORMATS = (*VIDEO_FORMATS, "png")
SIZES = {"720p": (1280, 720), "1080p": (1920, 1080), "square": (1080, 1080)}
MAX_WIDTH, MAX_HEIGHT = 3840, 2160


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
    motion_ms: int = 400
    overlays: tuple[str, ...] = OVERLAYS
    footer: bool = True
    theme: str = "dark"

    def __post_init__(self) -> None:
        """Reject values that are out of range (``ExportError``)."""
        checks = (
            (self.view in VIEWS, f"view must be one of {', '.join(VIEWS)}"),
            (set(self.overlays) <= set(OVERLAYS), "unknown overlay"),
            (self.theme in THEMES, "theme must be dark or light"),
            (160 <= self.width <= MAX_WIDTH, "width out of range"),
            (120 <= self.height <= MAX_HEIGHT, "height out of range"),
            (1 <= self.fps <= 60, "fps must be 1-60"),
            (0.2 <= self.hold <= 30, "hold must be 0.2-30 seconds"),
            (0 <= self.motion_ms <= 2000, "motion must be 0-2000 ms"),
            (self.start >= 1, "events start at 1"),
        )
        for passed, message in checks:
            if not passed:
                raise ExportError(message)


def event_range(options: ExportOptions, total: int) -> tuple[int, int]:
    """(first, last) event numbers to show; ``ExportError`` if outside."""
    start, end = options.start, options.end or total
    if not 1 <= start <= end <= total:
        raise ExportError(f"events must satisfy 1 <= start <= end <= {total}")
    return start, end


def parse_size(text: str) -> tuple[int, int]:
    """(width, height) from a preset name or ``WxH``; ``ValueError`` if bad."""
    if text in SIZES:
        return SIZES[text]
    width, _, height = text.partition("x")
    if not (width.isdigit() and height.isdigit()):
        raise ValueError(f"bad size {text!r}: use 720p, 1080p, square or WxH")
    return int(width), int(height)


def options_from_request(data: dict[str, Any]) -> tuple[ExportOptions, str]:
    """Options and output format from a web request (untrusted JSON).

    Raises ``ExportError`` for anything unknown or out of range.
    """
    fmt = str(data.get("format", "mp4"))
    if fmt not in FORMATS:
        raise ExportError(f"format must be one of {', '.join(FORMATS)}")
    try:
        width, height = parse_size(str(data.get("size", "720p")))
        end = data.get("end")
        options = ExportOptions(
            view=str(data.get("view", "animation")),
            start=int(data.get("start", 1)),
            end=int(end) if end is not None else None,
            width=width,
            height=height,
            fps=int(data.get("fps", 30)),
            hold=float(data.get("hold", 1.2)),
            motion_ms=int(data.get("motion_ms", 400)),
            overlays=tuple(str(o) for o in data.get("overlays", OVERLAYS)),
            footer=bool(data.get("footer", True)),
            theme=str(data.get("theme", "dark")),
        )
    except (TypeError, ValueError) as error:
        raise ExportError(f"bad export options: {error}") from error
    return options, fmt
