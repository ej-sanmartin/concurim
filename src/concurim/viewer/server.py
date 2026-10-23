"""Local-only web viewer server (standard library only).

Security model: binds to loopback, rejects unexpected ``Host`` headers (DNS
rebinding), serves source text only from the loaded trace (never from the
filesystem), serves static assets from one directory with path containment,
and sends a strict Content-Security-Policy. It has no write endpoints.
"""

from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from concurim.recorder.serialization import Trace
from concurim.replay.engine import build_replay

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")
CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)


class ViewerServer(ThreadingHTTPServer):
    """HTTP server holding one prepared trace."""

    daemon_threads = True

    def __init__(
        self, trace: Trace, port: int = 0, static_dir: Path = STATIC_DIR
    ) -> None:
        self.replay_json = json.dumps(
            build_replay(trace), separators=(",", ":")
        ).encode()
        self.sources = trace.sources
        self.static_dir = static_dir.resolve()
        super().__init__(("127.0.0.1", port), _Handler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/"

    def host_allowed(self, host: str | None) -> bool:
        port = self.server_address[1]
        return host in {f"{h}:{port}" for h in LOOPBACK_HOSTS}


class _Handler(BaseHTTPRequestHandler):
    server_version = "Concurim"

    @property
    def viewer(self) -> ViewerServer:
        """The owning server, typed."""
        return cast(ViewerServer, self.server)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return None  # keep the terminal quiet

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if not self.viewer.host_allowed(self.headers.get("Host")):
            return self._send(HTTPStatus.FORBIDDEN, b"bad host", "text/plain")
        url = urlsplit(self.path)
        if url.path == "/api/replay":
            return self._send(
                HTTPStatus.OK, self.viewer.replay_json, "application/json"
            )
        if url.path == "/api/source":
            return self._source(parse_qs(url.query).get("path", [""])[0])
        return self._static(url.path)

    def do_HEAD(self) -> None:  # noqa: N802
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, b"", "text/plain")

    def _source(self, name: str) -> None:
        text = self.viewer.sources.get(name)  # dict lookup, no filesystem
        if text is None:
            return self._send(
                HTTPStatus.NOT_FOUND, b"no such source", "text/plain"
            )
        self._send(HTTPStatus.OK, text.encode(), "text/plain; charset=utf-8")

    def _static(self, path: str) -> None:
        rel = path.lstrip("/") or "index.html"
        root = self.viewer.static_dir
        target = (root / rel).resolve()
        if root not in target.parents or not target.is_file():
            return self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
        ctype = (
            mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        )
        self._send(HTTPStatus.OK, target.read_bytes(), ctype)

    def _send(self, status: HTTPStatus, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
