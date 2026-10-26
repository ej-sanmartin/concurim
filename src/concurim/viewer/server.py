"""Local-only web viewer server (standard library only).

Security model:

* Binds to loopback only and rejects unexpected ``Host`` headers (DNS
  rebinding).
* Every state-changing request (loading a trace, uploading files, running a
  program) must carry the per-launch token, which only the page served by
  this process can read, and any ``Origin`` header must be this server.
  A web page on another site therefore cannot trigger a run.
* Source text is served only from the loaded trace (never from disk);
  static assets come from one directory with path containment.
* Request bodies are size-limited per route; a strict CSP is always sent.
"""

from __future__ import annotations

import mimetypes
import secrets
from collections.abc import Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qsl, urlsplit

from concurim.recorder.serialization import Trace
from concurim.viewer.api import Response, find_route, ok, run_route
from concurim.viewer.runs import RunManager
from concurim.viewer.session import Session
from concurim.viewer.workspaces import Workspaces

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")
TOKEN_HEADER = "X-Concurim-Token"  # noqa: S105 - a header name
TOKEN_PLACEHOLDER = b"__CONCURIM_TOKEN__"
CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)


class ViewerServer(ThreadingHTTPServer):
    """HTTP server for the viewer; the shown trace can change at runtime."""

    daemon_threads = True

    def __init__(
        self,
        trace: Trace | None = None,
        port: int = 0,
        *,
        label: str = "trace",
        compare: Sequence[tuple[Trace, str]] = (),
        static_dir: Path = STATIC_DIR,
        project_dir: Path | None = None,
    ) -> None:
        self.session = Session()
        if trace is not None:
            self.session.load(trace, label)
        # Two recordings shown side by side; independent of ``session``.
        self.compare = {"a": Session(), "b": Session()}
        for slot, (loaded, name) in zip("ab", compare, strict=False):
            self.compare[slot].load(loaded, name)
        self.token = secrets.token_urlsafe(32)
        self.workspaces = Workspaces()
        self.runs = RunManager(self.workspaces, self.session.load)
        self.project_dir = (project_dir or Path.cwd()).resolve()
        self.static_dir = static_dir.resolve()
        super().__init__(("127.0.0.1", port), _Handler)

    @property
    def url(self) -> str:
        """Address of the viewer's home page."""
        return f"http://127.0.0.1:{self.server_address[1]}/"

    def host_allowed(self, host: str | None) -> bool:
        """Whether the ``Host`` header names this loopback server."""
        port = self.server_address[1]
        return host in {f"{h}:{port}" for h in LOOPBACK_HOSTS}

    def origin_allowed(self, origin: str | None) -> bool:
        """Missing Origin is fine (non-browser); otherwise it must be us."""
        port = self.server_address[1]
        return origin is None or origin in {
            f"http://{h}:{port}" for h in LOOPBACK_HOSTS
        }

    def server_close(self) -> None:
        """Stop any running program, delete scratch files, close the socket."""
        self.runs.shutdown()
        super().server_close()


class _Handler(BaseHTTPRequestHandler):
    server_version = "Concurim"

    @property
    def viewer(self) -> ViewerServer:
        """The owning server, typed."""
        return cast(ViewerServer, self.server)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return None  # keep the terminal quiet

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if not self._host_ok():
            return
        url = urlsplit(self.path)
        if url.path.startswith("/api/"):
            return self._api("GET", url.path, url.query)
        self._static(url.path)

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_ok():
            return
        srv = self.viewer
        if not srv.origin_allowed(self.headers.get("Origin")):
            return self._send_response(ok({"error": "bad origin"}, 403))
        sent = self.headers.get(TOKEN_HEADER, "")
        if not secrets.compare_digest(sent.encode(), srv.token.encode()):
            return self._send_response(ok({"error": "missing token"}, 403))
        url = urlsplit(self.path)
        self._api("POST", url.path, url.query)

    def do_HEAD(self) -> None:  # noqa: N802
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, b"", "text/plain")

    def _host_ok(self) -> bool:
        if self.viewer.host_allowed(self.headers.get("Host")):
            return True
        self._send(HTTPStatus.FORBIDDEN, b"bad host", "text/plain")
        return False

    def _api(self, method: str, path: str, raw_query: str) -> None:
        route = find_route(method, path)
        if route is None:
            return self._send_response(ok({"error": "not found"}, 404))
        handler, match, limit = route
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= limit:
            self.close_connection = True  # do not read an oversized body
            status = 413 if length > limit else 400
            return self._send_response(ok({"error": "bad body size"}, status))
        body = self.rfile.read(length) if length else b""
        query = dict(parse_qsl(raw_query))
        self._send_response(run_route(self.viewer, handler, match, query, body))

    def _static(self, path: str) -> None:
        rel = path.lstrip("/") or "index.html"
        root = self.viewer.static_dir
        target = (root / rel).resolve()
        if root not in target.parents or not target.is_file():
            return self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
        ctype = (
            mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        )
        data = target.read_bytes()
        if target.name == "index.html":
            data = data.replace(TOKEN_PLACEHOLDER, self.viewer.token.encode())
        self._send(HTTPStatus.OK, data, ctype)

    def _send_response(self, response: Response) -> None:
        self._send(HTTPStatus(response.status), response.body, response.ctype)

    def _send(self, status: HTTPStatus, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
