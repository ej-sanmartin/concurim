"""The ``concurim export`` subcommand."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from concurim.export.cdp import ExportError
from concurim.export.options import (
    OVERLAYS,
    THEMES,
    VIEWS,
    ExportOptions,
    parse_size,
)
from concurim.export.video import export_video
from concurim.recorder.serialization import load_trace

VIDEO_WARNING = (
    "Note: videos show everything in the picture: file paths, thread "
    "names and (in the code view) source. Review a clip before sharing it."
)


def add_parser(sub: argparse._SubParsersAction) -> None:
    """Register ``export`` on the CLI's subparsers."""
    cmd = sub.add_parser(
        "export",
        help="render a recording as .mp4/.webm/.gif or a PNG directory",
    )
    cmd.add_argument("trace", type=Path)
    cmd.add_argument("-o", "--output", type=Path, required=True)
    cmd.add_argument("--view", choices=VIEWS, default="animation")
    cmd.add_argument("--events", metavar="A:B", help="1-based, inclusive")
    cmd.add_argument("--size", default="720p", help="720p, 1080p, square, WxH")
    cmd.add_argument("--fps", type=int, default=30)
    cmd.add_argument(
        "--hold",
        type=float,
        default=1.2,
        help="seconds each event stays on screen",
    )
    cmd.add_argument(
        "--motion",
        type=int,
        default=400,
        metavar="MS",
        help="milliseconds of glide between events (0: straight cuts)",
    )
    cmd.add_argument(
        "--hide",
        action="append",
        default=[],
        choices=OVERLAYS,
        help="leave out an overlay (repeatable)",
    )
    cmd.add_argument("--no-footer", action="store_true")
    cmd.add_argument(
        "--no-watermark",
        action="store_true",
        help="leave the logo and name off the picture",
    )
    cmd.add_argument("--theme", choices=THEMES, default="dark")
    cmd.set_defaults(func=run)


def _parse_events(text: str | None) -> tuple[int, int | None]:
    """1-based (first, last) from ``A:B``; last None means the end."""
    if not text:
        return 1, None
    first, _, last = text.partition(":")
    if not first.isdigit() or (last and not last.isdigit()):
        raise ValueError(f"bad --events {text!r}: use A:B, e.g. 5:40")
    return int(first), int(last) if last else None


def run(args: argparse.Namespace) -> int:
    """Render a trace to a clip; returns 2 on a user-fixable problem."""
    try:
        width, height = parse_size(args.size)
        start, end = _parse_events(args.events)
        options = ExportOptions(
            view=args.view,
            start=start,
            end=end,
            width=width,
            height=height,
            fps=args.fps,
            hold=args.hold,
            motion_ms=args.motion,
            footer=not args.no_footer,
            watermark=not args.no_watermark,
            overlays=tuple(o for o in OVERLAYS if o not in args.hide),
            theme=args.theme,
        )
        trace = load_trace(args.trace)

        def progress(done: int, total: int) -> None:
            print(f"\revent {done}/{total}", end="", file=sys.stderr)

        count = export_video(
            trace, args.trace.name, args.output, options, progress
        )
    except (ExportError, ValueError) as error:
        print(f"\nconcurim: error: {error}", file=sys.stderr)
        return 2
    print(f"\nconcurim: wrote {count} events to {args.output}", file=sys.stderr)
    print(VIDEO_WARNING, file=sys.stderr)
    return 0
