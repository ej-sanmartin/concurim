"""Command-line interface: record, view, demo, inspect."""

from __future__ import annotations

import argparse
import sys
import tempfile
import webbrowser
from collections.abc import Sequence
from pathlib import Path

from concurim import __version__
from concurim.config import RecorderConfig
from concurim.instrumentation.auto import LEVELS
from concurim.recorder.events import TraceFormatError
from concurim.recorder.serialization import Trace, load_trace
from concurim.samples import sample_file

SHARING_WARNING = (
    "Note: traces can contain file paths, thread names and (if enabled) "
    "source code or payload previews. Review a trace before sharing it."
)
VIDEO_WARNING = (
    "Note: videos show everything in the picture: file paths, thread "
    "names and (in the code view) source. Review a clip before sharing it."
)
SIZES = {"720p": (1280, 720), "1080p": (1920, 1080), "square": (1080, 1080)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="concurim", description="See how Python runs together."
    )
    parser.add_argument(
        "--version", action="version", version=f"concurim {__version__}"
    )
    _add_server_options(parser)
    parser.set_defaults(func=_cmd_home)
    sub = parser.add_subparsers(dest="command")

    rec = sub.add_parser(
        "record",
        help="run a script and record instrumented activity",
        description="Run SCRIPT and record activity on Concurim-instrumented "
        "objects. Options must come before SCRIPT; everything after SCRIPT "
        "is passed to it unchanged.",
    )
    rec.add_argument(
        "-o",
        "--output",
        type=Path,
        help="trace path (default: <script>.concurim)",
    )
    rec.add_argument(
        "--include-source",
        action="store_true",
        help="embed project source files in the trace",
    )
    rec.add_argument(
        "--preview",
        action="store_true",
        help="record bounded previews of primitive payloads",
    )
    rec.add_argument(
        "--auto",
        choices=LEVELS,
        default="threads",
        help="automatic instrumentation: none (only Concurim objects), "
        "threads (default), queues (threads + queue.Queue)",
    )
    rec.add_argument("--max-events", type=int, default=1_000_000)
    rec.add_argument(
        "--light",
        action="store_true",
        help="lightweight mode: no source locations",
    )
    rec.add_argument("script", type=Path)
    rec.add_argument("script_args", nargs=argparse.REMAINDER)
    rec.set_defaults(func=_cmd_record)

    for name, func, help_ in (
        ("view", _cmd_view, "open a recorded trace"),
        ("compare", _cmd_compare, "show two recordings side by side"),
        ("demo", _cmd_demo, "record and view a demo"),
    ):
        cmd = sub.add_parser(name, help=help_)
        if name == "view":
            cmd.add_argument("trace", type=Path)
        if name == "compare":
            cmd.add_argument("first", type=Path)
            cmd.add_argument("second", type=Path)
        _add_server_options(cmd)
        cmd.set_defaults(func=func)

    _add_export_parser(sub)
    insp = sub.add_parser("inspect", help="print trace metadata")
    insp.add_argument("trace", type=Path)
    insp.set_defaults(func=_cmd_inspect)
    return parser


def _add_export_parser(sub: argparse._SubParsersAction) -> None:
    """Register ``export`` (arguments: see ``--help``)."""
    from concurim.export.video import OVERLAYS, VIEWS

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
        "--hide",
        action="append",
        default=[],
        choices=OVERLAYS,
        help="leave out an overlay (repeatable)",
    )
    cmd.add_argument("--no-footer", action="store_true")
    cmd.add_argument("--theme", choices=("dark", "light"), default="dark")
    cmd.set_defaults(func=_cmd_export)


def _parse_size(text: str) -> tuple[int, int]:
    """(width, height) from a preset name or ``WxH``; ValueError if bad."""
    if text in SIZES:
        return SIZES[text]
    width, _, height = text.partition("x")
    if not (width.isdigit() and height.isdigit()):
        raise ValueError(f"bad --size {text!r}: use 720p, 1080p or WxH")
    return int(width), int(height)


def _parse_events(text: str | None) -> tuple[int, int | None]:
    """1-based (first, last) from ``A:B``; last None means the end."""
    if not text:
        return 1, None
    first, _, last = text.partition(":")
    if not first.isdigit() or (last and not last.isdigit()):
        raise ValueError(f"bad --events {text!r}: use A:B, e.g. 5:40")
    return int(first), int(last) if last else None


def _cmd_export(args: argparse.Namespace) -> int:
    """Render a trace to a clip; returns 2 on a user-fixable problem."""
    from concurim.export.cdp import ExportError
    from concurim.export.video import OVERLAYS, ExportOptions, export_video

    try:
        width, height = _parse_size(args.size)
        start, end = _parse_events(args.events)
        options = ExportOptions(
            view=args.view,
            start=start,
            end=end,
            width=width,
            height=height,
            fps=args.fps,
            hold=args.hold,
            footer=not args.no_footer,
            overlays=tuple(o for o in OVERLAYS if o not in args.hide),
            theme=args.theme,
        )
        frames = export_video(
            args.trace,
            args.output,
            options,
            lambda msg: print(f"\r{msg}", end="", file=sys.stderr),
        )
    except (ExportError, ValueError) as error:
        print(f"\nconcurim: error: {error}", file=sys.stderr)
        return 2
    print(
        f"\nconcurim: wrote {frames} frames to {args.output}", file=sys.stderr
    )
    print(VIDEO_WARNING, file=sys.stderr)
    return 0


def _add_server_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="port to serve on (default: any free port)",
    )
    parser.add_argument("--no-browser", action="store_true")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns the process exit status."""
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (TraceFormatError, FileNotFoundError) as error:
        print(f"concurim: error: {error}", file=sys.stderr)
        return 2


def _cmd_record(args: argparse.Namespace) -> int:
    from concurim.runner import run_recorded

    script: Path = args.script
    if not script.is_file():
        raise FileNotFoundError(f"script not found: {script}")
    output = args.output or Path(f"{script.stem}.concurim")
    config = RecorderConfig(
        max_events=args.max_events,
        include_source=args.include_source,
        preview=args.preview,
        capture_source_locations=not args.light,
        auto=args.auto,
        # Paths are shown relative to the script, wherever it is run from.
        source_root=str(script.resolve().parent),
    )
    code, count = run_recorded(script, args.script_args, output, config)
    print(f"concurim: recorded {count} events to {output}", file=sys.stderr)
    print(f"concurim: view it with: concurim view {output}", file=sys.stderr)
    print(SHARING_WARNING, file=sys.stderr)
    return code


def _serve(
    trace: Trace | None,
    port: int,
    open_browser: bool,
    label: str = "trace",
    compare: tuple[tuple[Trace, str], ...] = (),
) -> int:
    from concurim.viewer.server import ViewerServer

    if not (Path(__file__).parent / "viewer/static/index.html").is_file():
        raise FileNotFoundError("viewer assets missing (run scripts/build.sh)")
    server = ViewerServer(trace, port, label=label, compare=compare)
    url = server.url + ("?compare=1" if compare else "")
    print(f"concurim: viewer at {url} (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nconcurim: stopped")
    finally:
        server.server_close()
    return 0


def _cmd_home(args: argparse.Namespace) -> int:
    return _serve(None, args.port, not args.no_browser)


def _cmd_view(args: argparse.Namespace) -> int:
    return _serve(
        load_trace(args.trace), args.port, not args.no_browser, args.trace.name
    )


def _cmd_compare(args: argparse.Namespace) -> int:
    pair = tuple((load_trace(p), p.name) for p in (args.first, args.second))
    return _serve(None, args.port, not args.no_browser, compare=pair)


def _cmd_demo(args: argparse.Namespace) -> int:
    from concurim.runner import run_recorded

    script = sample_file("threaded_pipeline.py")
    out = Path(tempfile.mkdtemp(prefix="concurim-demo-")) / "demo.concurim"
    # The bundled example is trusted, so its source is embedded.
    config = RecorderConfig(include_source=True, source_root=str(script.parent))
    code, count = run_recorded(script, [], out, config)
    print(f"concurim: recorded {count} events from {script.name}")
    if code != 0:
        return code
    return _serve(load_trace(out), args.port, not args.no_browser, script.name)


def _cmd_inspect(args: argparse.Namespace) -> int:
    trace = load_trace(args.trace)
    meta = trace.metadata
    env = meta.get("environment", {})
    print(f"trace:          {args.trace}")
    print(
        f"concurim:       {meta.get('concurim_version')} "
        f"(format {meta.get('format_version')})"
    )
    print(f"recorded:       {meta.get('created_at_utc')}")
    print(f"duration:       {meta.get('duration_ns', 0) / 1e9:.3f}s")
    print(f"events:         {len(trace.events)}")
    print(
        f"python:         {env.get('implementation')} "
        f"{env.get('python_version')} on {env.get('platform')} "
        f"(free-threaded build: {env.get('free_threaded_build')}, "
        f"GIL enabled: {env.get('gil_enabled')})"
    )
    print(f"sources:        {len(trace.sources)} embedded")
    if meta.get("truncated"):
        print(
            f"WARNING:        truncated, {meta.get('dropped_events')} "
            "events dropped (buffer limit)"
        )
    coverage = meta.get("coverage", {})
    for key in ("observed", "not_observed"):
        print(f"{key.replace('_', ' ')}:")
        for line in coverage.get(key, []):
            print(f"  - {line}")
    return 0
