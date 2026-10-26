"""Export a recording as a video, GIF or PNG sequence.

The real viewer is rendered in a headless browser in *capture mode* (see
``frontend/src/capture.ts``). Time is explicit: the exporter shows an event,
then advances the page's clock by exactly one frame at a time, so the glide
of a token between two events is the same on every run. Frames go to ffmpeg,
or to PNG files. Exporting only loads a trace; it never runs the program.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlencode

from concurim.export.cdp import Browser, ExportError, find_browser
from concurim.export.options import ExportOptions, event_range
from concurim.export.sink import FrameSink
from concurim.recorder.serialization import Trace

_READY_TIMEOUT_S = 20.0

Progress = Callable[[int, int], None]


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


def _frames_per_event(options: ExportOptions) -> tuple[int, int]:
    """(total frames, gliding frames) an event occupies in the clip."""
    total = max(1, round(options.hold * options.fps))
    glide = math.ceil(options.motion_ms * options.fps / 1000)
    return total, min(glide, total - 1)


def _shoot_event(
    browser: Browser,
    sink: FrameSink,
    index: int,
    options: ExportOptions,
    glide: bool,
) -> None:
    """Show event ``index``: glide frames from the last state, then hold."""
    total, tween = _frames_per_event(options)
    browser.evaluate(f"window.__concurim.seek({index})")
    if glide:
        step = 1000 / options.fps
        for _ in range(tween):
            browser.evaluate(f"window.__concurim.advance({step})")
            sink.write(browser.screenshot())
        total -= tween
    browser.evaluate("window.__concurim.settle()")
    sink.write(browser.screenshot(), repeat=total)


def export_video(
    trace: Trace,
    name: str,
    output: Path,
    options: ExportOptions,
    progress: Progress | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> int:
    """Render ``trace`` to ``output``; return the number of events shown.

    The output kind follows the suffix (.mp4, .webm, .gif) or is a directory
    of PNG frames. ``progress(done, total)`` is called after each event;
    ``cancelled()`` is polled between events. Raises ``ExportError`` for
    fixable problems.
    """
    from concurim.viewer.server import ViewerServer

    server = ViewerServer(trace, 0, label=name)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sink = browser = None
    try:
        total = server.session.event_count
        start, end = event_range(options, total)
        sink = FrameSink(output, options.fps)
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
            "motion": str(options.motion_ms),
            "footer": _footer(name, start, end, total, server.session.digest)
            if options.footer
            else "",
        }
        browser.page(
            "Page.navigate", {"url": f"{server.url}?{urlencode(query)}"}
        )
        _wait_ready(browser)
        browser.evaluate(f"window.__concurim.seek({start - 1})")
        browser.evaluate("window.__concurim.settle()")
        count = end - start + 1
        for n, index in enumerate(range(start - 1, end)):
            if cancelled():
                raise ExportError("export cancelled")
            _shoot_event(browser, sink, index, options, glide=n > 0)
            if progress:
                progress(n + 1, count)
        sink.close()
        return count
    except BaseException:
        if sink:
            sink.abort()
        raise
    finally:
        if browser:
            browser.close()
        server.shutdown()
        server.server_close()
