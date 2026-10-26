"""JSON API routes for the local viewer.

Every route is listed in ``ROUTES`` with the largest request body it will
accept. Mutating routes (POST) are additionally protected by the server's
token and Origin checks; see ``server.py``.
"""

from __future__ import annotations

import io
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from concurim import __version__
from concurim.export.cdp import ExportError
from concurim.recorder.events import TraceFormatError
from concurim.recorder.serialization import load_trace
from concurim.samples import find_sample, load_manifest, sample_file
from concurim.viewer import interpreters
from concurim.viewer.exports import (
    ExportConflict,
    ExportNotFound,
    capabilities,
)
from concurim.viewer.runs import RunConflict, RunError
from concurim.viewer.workspaces import WorkspaceError

if TYPE_CHECKING:
    from concurim.viewer.server import ViewerServer

KIB, MIB = 1024, 1024 * 1024
MAX_TRACE_UPLOAD = 256 * MIB
MAX_UPLOAD_JSON = 96 * MIB  # base64 inflates the 64 MiB workspace limit
MAX_SMALL_JSON = 64 * KIB


@dataclass(frozen=True)
class Response:
    """An HTTP response produced by a route."""

    status: int
    body: bytes
    ctype: str = "application/json"
    filename: str | None = None  # set: sent as a download


class ApiError(Exception):
    """A request that is rejected with ``status`` and a message."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def ok(data: Any, status: int = 200) -> Response:
    """JSON response."""
    return Response(status, json.dumps(data, separators=(",", ":")).encode())


def _object(body: bytes) -> dict[str, Any]:
    try:
        data = json.loads(body or b"{}")
    except ValueError as exc:
        raise ApiError(400, "invalid JSON") from exc
    if not isinstance(data, dict):
        raise ApiError(400, "expected a JSON object")
    return data


Handler = Callable[
    ["ViewerServer", "re.Match[str]", dict[str, str], bytes], Response
]


def _session(srv: ViewerServer, *_: object) -> Response:
    manifest = load_manifest()
    keys = ("id", "title", "observability", "summary", "watch")
    return ok(
        {
            "version": __version__,
            "has_trace": srv.session.has_trace,
            "label": srv.session.label,
            "generation": srv.session.generation,
            "compare": {k: s.label for k, s in srv.compare.items()},
            "samples": [{k: s[k] for k in keys} for s in manifest["samples"]],
            "planned": manifest["planned"],
            "interpreters": interpreters.discover(srv.project_dir),
            "cwd": str(srv.project_dir),
            "export": capabilities(),
        }
    )


def _replay(srv: ViewerServer, *_: object) -> Response:
    if srv.session.replay_json is None:
        raise ApiError(404, "no trace loaded")
    return Response(200, srv.session.replay_json)


def _source(
    srv: ViewerServer, _m: Any, query: dict[str, str], _b: bytes
) -> Response:
    text = srv.session.sources.get(query.get("path", ""))  # dict, no disk
    if text is None:
        raise ApiError(404, "no such source")
    return Response(200, text.encode(), "text/plain; charset=utf-8")


def _sample(m: re.Match[str]) -> dict[str, Any]:
    entry = find_sample(unquote(m["id"]))
    if entry is None:
        raise ApiError(404, "no such sample")
    return entry


def _sample_source(srv: ViewerServer, m: re.Match[str], *_: object) -> Response:
    text = sample_file(_sample(m)["source"]).read_text("utf-8")
    return Response(200, text.encode(), "text/plain; charset=utf-8")


def _sample_open(srv: ViewerServer, m: re.Match[str], *_: object) -> Response:
    entry = _sample(m)
    srv.session.load(load_trace(sample_file(entry["trace"])), entry["title"])
    return ok({"ok": True})


def _trace_upload(
    srv: ViewerServer, _m: Any, query: dict[str, str], body: bytes
) -> Response:
    name = re.sub(r"[^\w .-]", "", query.get("name", ""))[:80] or "trace"
    srv.session.load(load_trace(io.BytesIO(body)), name)
    return ok({"ok": True})


def _compare_upload(
    srv: ViewerServer, m: re.Match[str], query: dict[str, str], body: bytes
) -> Response:
    name = re.sub(r"[^\w .-]", "", query.get("name", ""))[:80] or "trace"
    srv.compare[m["slot"]].load(load_trace(io.BytesIO(body)), name)
    return ok({"ok": True})


def _compare_replay(
    srv: ViewerServer, m: re.Match[str], *_: object
) -> Response:
    replay = srv.compare[m["slot"]].replay_json
    if replay is None:
        raise ApiError(404, "no trace loaded in this slot")
    return Response(200, replay)


def _workspace_create(
    srv: ViewerServer, _m: Any, _q: Any, body: bytes
) -> Response:
    return ok(srv.workspaces.create(_object(body).get("files")), 201)


def _run_plan(srv: ViewerServer, _m: Any, _q: Any, body: bytes) -> Response:
    return ok(srv.runs.plan(_object(body)), 201)


def _run_start(srv: ViewerServer, m: re.Match[str], *_: object) -> Response:
    return ok(srv.runs.start(m["id"]), 202)


def _run_status(srv: ViewerServer, m: re.Match[str], *_: object) -> Response:
    return ok(srv.runs.status(m["id"]))


def _run_cancel(srv: ViewerServer, m: re.Match[str], *_: object) -> Response:
    return ok(srv.runs.cancel(m["id"]))


def _run_snapshot(srv: ViewerServer, m: re.Match[str], *_: object) -> Response:
    return ok(srv.runs.open_snapshot(m["id"]))


def _export_start(srv: ViewerServer, _m: Any, _q: Any, body: bytes) -> Response:
    return ok(srv.exports.start(_object(body)), 202)


def _export_status(srv: ViewerServer, m: re.Match[str], *_: object) -> Response:
    return ok(srv.exports.status(m["id"]))


def _export_cancel(srv: ViewerServer, m: re.Match[str], *_: object) -> Response:
    return ok(srv.exports.cancel(m["id"]))


def _export_file(srv: ViewerServer, m: re.Match[str], *_: object) -> Response:
    name, data, ctype = srv.exports.file(m["id"])
    return Response(200, data, ctype, name)


# (method, path regex, handler, max request body in bytes)
ROUTES: list[tuple[str, str, Handler, int]] = [
    ("GET", r"/api/session", _session, 0),
    ("GET", r"/api/replay", _replay, 0),
    ("GET", r"/api/source", _source, 0),
    ("GET", r"/api/samples/(?P<id>[\w%.-]+)/source", _sample_source, 0),
    ("POST", r"/api/samples/(?P<id>[\w%.-]+)/open", _sample_open, 0),
    ("POST", r"/api/trace", _trace_upload, MAX_TRACE_UPLOAD),
    (
        "POST",
        r"/api/compare/(?P<slot>[ab])/trace",
        _compare_upload,
        MAX_TRACE_UPLOAD,
    ),
    ("GET", r"/api/compare/(?P<slot>[ab])/replay", _compare_replay, 0),
    ("POST", r"/api/workspaces", _workspace_create, MAX_UPLOAD_JSON),
    ("POST", r"/api/runs/plan", _run_plan, MAX_SMALL_JSON),
    ("POST", r"/api/runs/(?P<id>\w+)/start", _run_start, MAX_SMALL_JSON),
    ("GET", r"/api/runs/(?P<id>\w+)", _run_status, 0),
    ("POST", r"/api/runs/(?P<id>\w+)/cancel", _run_cancel, 0),
    ("POST", r"/api/runs/(?P<id>\w+)/snapshot", _run_snapshot, 0),
    ("POST", r"/api/export", _export_start, MAX_SMALL_JSON),
    ("GET", r"/api/export/(?P<id>\w+)", _export_status, 0),
    ("POST", r"/api/export/(?P<id>\w+)/cancel", _export_cancel, 0),
    ("GET", r"/api/export/(?P<id>\w+)/file", _export_file, 0),
]
_COMPILED = [(m, re.compile(p), h, n) for m, p, h, n in ROUTES]


def find_route(
    method: str, path: str
) -> tuple[Handler, re.Match[str], int] | None:
    """Match a request to a route; ``None`` if it is not an API path."""
    for route_method, pattern, handler, limit in _COMPILED:
        match = pattern.fullmatch(path)
        if match and route_method == method:
            return handler, match, limit
    return None


def run_route(
    srv: ViewerServer,
    handler: Handler,
    match: re.Match[str],
    query: dict[str, str],
    body: bytes,
) -> Response:
    """Execute a route, mapping domain errors to HTTP statuses."""
    try:
        return handler(srv, match, query, body)
    except ApiError as exc:
        return ok({"error": str(exc)}, exc.status)
    except (RunConflict, ExportConflict) as exc:
        return ok({"error": str(exc)}, 409)
    except ExportNotFound as exc:
        return ok({"error": str(exc)}, 404)
    except (RunError, WorkspaceError, TraceFormatError, ExportError) as exc:
        return ok({"error": str(exc)}, 400)
