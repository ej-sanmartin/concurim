import http.client
import json
import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from concurim.cli import main
from concurim.recorder.serialization import load_trace
from concurim.viewer.server import ViewerServer

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "src" / "concurim" / "samples"


def run_cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "concurim", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=60,
    )


SCRIPT = textwrap.dedent("""
    import os, sys
    from concurim import TracedQueue
    q = TracedQueue(maxsize=1, name="Args")
    q.put(sys.argv[1:])
    print("args=" + ",".join(sys.argv[1:]), "cwd=" + os.getcwd())
    sys.exit(int(os.environ.get("EXIT", "0")))
""")


def test_record_preserves_args_cwd_and_exit_status(tmp_path):
    (tmp_path / "prog.py").write_text(SCRIPT)
    r = run_cli(
        "record",
        "-o",
        "out.concurim",
        "prog.py",
        "a",
        "--output",
        "b",
        cwd=tmp_path,
    )
    assert r.returncode == 0, r.stderr
    # options after the script belong to the script, untouched
    assert "args=a,--output,b" in r.stdout
    assert f"cwd={os.path.realpath(tmp_path)}" in r.stdout
    trace = load_trace(tmp_path / "out.concurim")
    assert trace.metadata["program"]["exit_code"] == 0
    assert any(e.event_type == "queue.put.completed" for e in trace.events)


def test_record_propagates_nonzero_exit_and_still_writes_trace(tmp_path):
    (tmp_path / "prog.py").write_text(SCRIPT)
    env = dict(os.environ, EXIT="3")
    r = subprocess.run(
        [sys.executable, "-m", "concurim", "record", "prog.py"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 3
    assert (
        load_trace(tmp_path / "prog.concurim").metadata["program"]["exit_code"]
        == 3
    )


def test_record_reports_script_exceptions(tmp_path):
    (tmp_path / "bad.py").write_text("raise RuntimeError('boom')\n")
    r = run_cli("record", "bad.py", cwd=tmp_path)
    assert r.returncode == 1 and "RuntimeError: boom" in r.stderr
    meta = load_trace(tmp_path / "bad.concurim").metadata
    assert meta["program"]["exception"] == "RuntimeError"


def test_record_waits_for_non_daemon_threads(tmp_path):
    (tmp_path / "late.py").write_text(
        textwrap.dedent("""
        import threading, time
        from concurim import TracedQueue
        q = TracedQueue()
        def later():
            time.sleep(0.2); q.put("late")
        threading.Thread(target=later).start()
    """)
    )
    run_cli("record", "late.py", cwd=tmp_path)
    ev = load_trace(tmp_path / "late.concurim").events
    assert any(e.event_type == "queue.put.completed" for e in ev)


def test_record_refuses_a_program_that_does_not_compile(tmp_path):
    (tmp_path / "bad.py").write_text("def (\n")
    result = run_cli("record", "bad.py", cwd=tmp_path)
    assert result.returncode == 2
    assert "cannot run" in result.stderr
    assert not (tmp_path / "bad.concurim").exists()


def test_record_missing_script_and_bad_trace(tmp_path, capsys):
    assert main(["record", str(tmp_path / "nope.py")]) == 2
    bad = tmp_path / "bad.concurim"
    bad.write_text("x")
    assert main(["inspect", str(bad)]) == 2
    assert "error" in capsys.readouterr().err


def test_bundled_example_records_and_inspects(tmp_path):
    out = tmp_path / "ex.concurim"
    r = run_cli(
        "record",
        "-o",
        str(out),
        "--include-source",
        str(SAMPLES / "threaded_pipeline.py"),
    )
    assert r.returncode == 0, r.stderr
    assert "processed 12 jobs" in r.stdout
    info = run_cli("inspect", str(out))
    assert info.returncode == 0 and "events:" in info.stdout
    assert "not observed" in info.stdout


@pytest.fixture
def server(tmp_path):
    out = tmp_path / "ex.concurim"
    r = run_cli(
        "record",
        "-o",
        str(out),
        "--include-source",
        str(SAMPLES / "threaded_pipeline.py"),
        cwd=ROOT,
    )
    assert r.returncode == 0, r.stderr
    srv = ViewerServer(load_trace(out), port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def get(srv, path, host=None):
    port = srv.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("GET", path, skip_host=True)
    conn.putheader("Host", host or f"127.0.0.1:{port}")
    conn.endheaders()
    resp = conn.getresponse()
    return resp.status, resp.read(), dict(resp.getheaders())


def test_viewer_serves_replay_index_and_sources(server):
    status, body, headers = get(server, "/api/replay")
    assert status == 200
    data = json.loads(body)
    assert data["summary"]["event_count"] == len(data["frames"])
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert server.server_address[0] == "127.0.0.1"
    assert get(server, "/")[0] == 200
    src = data["source_paths"][0]
    status, body, _ = get(server, f"/api/source?path={src}")
    assert status == 200 and b"def producer" in body


@pytest.mark.parametrize(
    "path",
    [
        "/api/source?path=/etc/passwd",
        "/api/source?path=../../etc/passwd",
        "/api/source?path=pyproject.toml",
        "/../../../etc/passwd",
        "/..%2f..%2f..%2fetc/passwd",
        "/%2e%2e/%2e%2e/etc/passwd",
        "/assets/../../../pyproject.toml",
    ],
)
def test_viewer_never_serves_files_outside_trace_and_static(server, path):
    status, body, _ = get(server, path)
    assert status == 404
    assert b"root:" not in body and b"[project]" not in body


def test_viewer_rejects_foreign_host_header(server):
    assert get(server, "/api/replay", host="evil.example:80")[0] == 403
    assert get(server, "/api/replay", host="localhost")[0] == 403


def test_compare_command_preloads_both_recordings(tmp_path, monkeypatch):
    seen = {}

    def fake_serve(self):  # stands in for serve_forever
        seen["compare"] = {k: s.label for k, s in self.compare.items()}
        seen["has_trace"] = self.session.has_trace
        raise KeyboardInterrupt

    monkeypatch.setattr(ViewerServer, "serve_forever", fake_serve)
    first, second = (
        SAMPLES / "shutdown.concurim",
        SAMPLES / "semaphore.concurim",
    )
    assert main(["compare", str(first), str(second), "--no-browser"]) == 0
    assert seen == {
        "compare": {"a": first.name, "b": second.name},
        "has_trace": False,
    }
    assert main(["compare", str(first), str(tmp_path / "no.concurim")]) == 2
