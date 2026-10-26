"""A tiny Chrome DevTools Protocol client over a pipe (standard library).

Chrome-family browsers started with ``--remote-debugging-pipe`` read JSON
commands from file descriptor 3 and answer on file descriptor 4, each
message ending in a NUL byte. That is all the exporter needs, so no browser
automation package is required. POSIX only (macOS and Linux).
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import select
import shutil
import signal
import tempfile
from pathlib import Path
from typing import Any

BROWSER_ENV = "CONCURIM_BROWSER"
_MAC_APPS = (
    "Google Chrome.app/Contents/MacOS/Google Chrome",
    "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "Chromium.app/Contents/MacOS/Chromium",
    "Brave Browser.app/Contents/MacOS/Brave Browser",
)
_PATH_NAMES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "microsoft-edge-stable",
    "brave-browser",
)
_TIMEOUT_S = 30.0


class ExportError(Exception):
    """A problem the user can fix (missing browser, missing ffmpeg, ...)."""


def find_browser() -> str:
    """Path of a Chrome-family browser.

    ``$CONCURIM_BROWSER`` wins; otherwise common install locations and
    ``PATH`` are searched. Raises ``ExportError`` with advice if none exists.
    """
    wanted = os.environ.get(BROWSER_ENV)
    if wanted:
        if shutil.which(wanted) or Path(wanted).is_file():
            return shutil.which(wanted) or wanted
        raise ExportError(f"{BROWSER_ENV}={wanted!r} is not an executable")
    for app in _MAC_APPS:
        for base in (Path("/Applications"), Path.home() / "Applications"):
            if (base / app).is_file():
                return str(base / app)
    for name in _PATH_NAMES:
        found = shutil.which(name)
        if found:
            return found
    raise ExportError(
        "no Chrome-family browser found. Install Google Chrome, Chromium "
        f"or Microsoft Edge, or set {BROWSER_ENV} to its executable."
    )


class Browser:
    """A headless browser with one page, driven over the DevTools pipe."""

    def __init__(self, executable: str, width: int, height: int) -> None:
        self._profile = tempfile.mkdtemp(prefix="concurim-browser-")
        self._next_id = 0
        self._buffer = b""
        to_browser_r, self._to_browser = os.pipe()
        self._from_browser, from_browser_w = os.pipe()
        args = [
            executable,
            "--headless=new",
            "--remote-debugging-pipe",
            f"--user-data-dir={self._profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--font-render-hinting=none",
            "--disable-background-timer-throttling",
            "--mute-audio",
            f"--window-size={width},{height}",
            "about:blank",
        ]
        actions = [
            (os.POSIX_SPAWN_DUP2, to_browser_r, 3),
            (os.POSIX_SPAWN_DUP2, from_browser_w, 4),
            # Browser chatter is not the user's business.
            (os.POSIX_SPAWN_OPEN, 1, os.devnull, os.O_WRONLY, 0),
            (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0),
        ]
        self._pid = os.posix_spawn(
            executable, args, os.environ, file_actions=actions
        )
        os.close(to_browser_r)
        os.close(from_browser_w)
        self._session = self._open_page(width, height)

    def _open_page(self, width: int, height: int) -> str:
        target = self.call("Target.createTarget", {"url": "about:blank"})
        attached = self.call(
            "Target.attachToTarget",
            {"targetId": target["targetId"], "flatten": True},
        )
        session = attached["sessionId"]
        self.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
            session,
        )
        self.call("Page.enable", session=session)
        return session

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        """Send one command and return its result (events are skipped)."""
        self._next_id += 1
        message: dict[str, Any] = {
            "id": self._next_id,
            "method": method,
            "params": params or {},
        }
        if session:
            message["sessionId"] = session
        os.write(self._to_browser, json.dumps(message).encode() + b"\0")
        while True:
            reply = self._read()
            if reply.get("id") != self._next_id:
                continue
            if "error" in reply:
                raise ExportError(f"{method}: {reply['error']}")
            return reply.get("result", {})

    def _read(self) -> dict[str, Any]:
        while b"\0" not in self._buffer:
            ready, _, _ = select.select(
                [self._from_browser], [], [], _TIMEOUT_S
            )
            chunk = os.read(self._from_browser, 1 << 16) if ready else b""
            if not chunk:
                raise ExportError("the browser stopped responding")
            self._buffer += chunk
        raw, self._buffer = self._buffer.split(b"\0", 1)
        return json.loads(raw)

    def page(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send a command to the page."""
        return self.call(method, params, self._session)

    def evaluate(self, expression: str) -> Any:
        """Run JavaScript in the page (awaiting promises); return the value."""
        out = self.page(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        if "exceptionDetails" in out:
            raise ExportError(f"page error: {out['exceptionDetails']}")
        return out["result"].get("value")

    def screenshot(self) -> bytes:
        """The visible page as PNG bytes."""
        out = self.page("Page.captureScreenshot", {"format": "png"})
        return base64.b64decode(out["data"])

    def close(self) -> None:
        """Stop the browser and delete its temporary profile."""
        for fd in (self._to_browser, self._from_browser):
            with contextlib.suppress(OSError):
                os.close(fd)
        try:
            os.kill(self._pid, signal.SIGTERM)
            os.waitpid(self._pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass
        shutil.rmtree(self._profile, ignore_errors=True)
