"""A tiny HTTP client and server fixture shared by the viewer API tests."""

from __future__ import annotations

import base64
import http.client
import json
import threading
import time

from concurim.viewer.server import ViewerServer


class Client:
    """Talks to a ``ViewerServer`` like the browser UI does."""

    def __init__(self, server: ViewerServer) -> None:
        self.server = server

    def request(
        self,
        method: str,
        path: str,
        body: bytes | dict | None = None,
        *,
        token: str | None = "default",
        host: str | None = None,
        origin: str | None = None,
        content_length: int | None = None,
    ) -> tuple[int, bytes, dict]:
        port = self.server.server_address[1]
        if isinstance(body, dict):
            body = json.dumps(body).encode()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        conn.putrequest(method, path, skip_host=True)
        conn.putheader("Host", host or f"127.0.0.1:{port}")
        if token == "default":
            token = self.server.token
        if token is not None:
            conn.putheader("X-Concurim-Token", token)
        if origin is not None:
            conn.putheader("Origin", origin)
        length = len(body or b"") if content_length is None else content_length
        if method == "POST":
            conn.putheader("Content-Length", str(length))
        conn.endheaders(body or None)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data, dict(resp.getheaders())

    def get_json(self, path: str) -> dict:
        status, data, _ = self.request("GET", path)
        assert status == 200, (status, data)
        return json.loads(data)

    def post_json(self, path: str, body: dict | bytes | None = None, **kw):
        status, data, _ = self.request("POST", path, body, **kw)
        return status, json.loads(data) if data else {}

    def upload(self, files: dict[str, str]) -> dict:
        """Create a workspace from ``{path: text}``."""
        payload = {
            "files": [
                {"path": p, "data": base64.b64encode(t.encode()).decode()}
                for p, t in files.items()
            ]
        }
        status, data = self.post_json("/api/workspaces", payload)
        assert status == 201, data
        return data

    def wait_run(self, run_id: str, timeout: float = 30.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.get_json(f"/api/runs/{run_id}")
            if run["state"] != "running":
                return run
            time.sleep(0.05)
        raise AssertionError("run did not finish in time")


def serve(tmp_path, trace=None):
    """Start a server on a free port in a background thread."""
    static = tmp_path / "static"
    static.mkdir(exist_ok=True)
    (static / "index.html").write_text(
        '<meta name="concurim-token" content="__CONCURIM_TOKEN__">'
    )
    server = ViewerServer(
        trace, port=0, static_dir=static, project_dir=tmp_path
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def stop(server: ViewerServer) -> None:
    server.shutdown()
    server.server_close()
