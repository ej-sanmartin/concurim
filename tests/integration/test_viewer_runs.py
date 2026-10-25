"""Recording a dropped program: plan, confirm, run, cancel, open."""

import sys
import textwrap
import time
from pathlib import Path

import pytest
from viewer_client import Client, serve, stop

PLAIN = textwrap.dedent(
    """
    import queue, sys, threading
    q = queue.Queue(maxsize=2)
    def worker():
        for _ in range(4):
            q.get(); q.task_done()
    t = threading.Thread(target=worker, name="worker")
    t.start()
    for n in range(4):
        q.put(n)
    t.join()
    print("done", sys.argv[1:])
    """
)


@pytest.fixture
def client(tmp_path):
    server = serve(tmp_path)
    yield Client(server)
    stop(server)


def plan(client, ws, **overrides):
    body = {"workspace_id": ws["id"], "entry": ws["suggested"], **overrides}
    status, data = client.post_json("/api/runs/plan", body)
    assert status == 201, data
    return data


def run_to_end(client, ws, **overrides):
    p = plan(client, ws, **overrides)
    status, started = client.post_json(f"/api/runs/{p['id']}/start")
    assert status == 202, started
    return p, client.wait_run(p["id"])


def test_dropped_file_is_not_executed_until_the_user_confirms(client, tmp_path):
    marker = tmp_path / "ran.txt"
    code = f"open({str(marker)!r}, 'w').write('x')\n"
    ws = client.upload({"main.py": code})
    p = plan(client, ws)
    assert not marker.exists()
    assert client.get_json("/api/session")["has_trace"] is False
    # The plan shows exactly what would run.
    assert p["script"].endswith("main.py") and p["cwd"].endswith(ws["id"])
    assert p["interpreter"] == sys.executable
    assert "<concurim bootstrap>" in p["command"]
    assert client.request("GET", f"/api/runs/{p['id']}")[0] == 400  # no run
    run_to_end_status, _ = client.post_json(f"/api/runs/{p['id']}/start")
    assert run_to_end_status == 202
    assert client.wait_run(p["id"])["state"] == "finished"
    assert marker.exists()


def test_recording_a_plain_program_opens_the_result(client):
    ws = client.upload({"main.py": PLAIN})
    p, run = run_to_end(client, ws, auto="queues", args="a 'b c'")
    assert run["state"] == "finished" and run["exit_code"] == 0
    assert "done ['a', 'b c']" in run["output"]
    assert run["trace_ready"] is True
    replay = client.get_json("/api/replay")
    assert replay["warnings"] == []
    assert len(replay["entities"]["queues"]) == 1
    assert replay["metadata"]["config"]["auto"] == "queues"
    assert client.get_json("/api/session")["label"] == "main.py"


def test_threads_level_does_not_claim_to_see_queues(client):
    ws = client.upload({"main.py": PLAIN})
    run_to_end(client, ws, auto="threads")
    replay = client.get_json("/api/replay")
    assert replay["entities"]["queues"] == {}
    assert any(
        "Plain queue.Queue" in s
        for s in replay["metadata"]["coverage"]["not_observed"]
    )


def test_source_is_embedded_only_when_asked(client):
    ws = client.upload({"main.py": PLAIN})
    run_to_end(client, ws, include_source=False)
    assert client.get_json("/api/replay")["source_paths"] == []
    run_to_end(client, ws, include_source=True)
    assert client.get_json("/api/replay")["source_paths"] == ["main.py"]


def test_failing_program_reports_exit_code_exception_and_still_opens(client):
    ws = client.upload({"main.py": "import threading\nraise KeyError('k')\n"})
    _, run = run_to_end(client, ws)
    assert run["state"] == "failed" and run["exit_code"] == 1
    assert run["exception"] == "KeyError"
    assert "KeyError" in run["output"]
    assert run["trace_ready"] is True


def test_exit_status_is_preserved(client):
    ws = client.upload({"main.py": "import sys\nsys.exit(7)\n"})
    _, run = run_to_end(client, ws)
    assert (run["state"], run["exit_code"]) == ("failed", 7)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows cannot send Ctrl-C to the program: cancel terminates it",
)
def test_cancel_interrupts_a_running_program_and_keeps_a_trace(client):
    code = (
        "import threading, time\nthreading.Thread(target=lambda: 1).start()\n"
    )
    code += "print('started', flush=True)\ntime.sleep(60)\n"
    ws = client.upload({"main.py": code})
    p = plan(client, ws)
    client.post_json(f"/api/runs/{p['id']}/start")
    # Second concurrent run is refused while one is active.
    other = plan(client, ws)
    assert client.post_json(f"/api/runs/{other['id']}/start")[0] == 409
    for _ in range(100):
        if "started" in client.get_json(f"/api/runs/{p['id']}")["output"]:
            break
        time.sleep(0.05)
    client.post_json(f"/api/runs/{p['id']}/cancel")
    run = client.wait_run(p["id"], timeout=15)
    assert run["state"] == "cancelled"
    assert run["trace_ready"] is True  # Ctrl-C still saves what was seen


def test_run_in_place_from_a_path_uses_the_files_own_directory(
    client, tmp_path
):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "helper.py").write_text("VALUE = 41\n")
    (proj / "app.py").write_text(
        "import os, helper\nprint(os.getcwd(), helper.VALUE + 1)\n"
    )
    status, p = client.post_json(
        "/api/runs/plan", {"script_path": str(proj / "app.py")}
    )
    assert status == 201 and p["cwd"] == str(proj.resolve())
    client.post_json(f"/api/runs/{p['id']}/start")
    run = client.wait_run(p["id"])
    assert run["state"] == "finished"
    assert f"{proj.resolve()} 42" in run["output"]


def test_interpreter_can_be_chosen_and_is_validated(client, tmp_path):
    ws = client.upload({"main.py": "print('hi')\n"})
    bad = client.post_json(
        "/api/runs/plan",
        {
            "workspace_id": ws["id"],
            "entry": "main.py",
            "interpreter": str(tmp_path / "no-python"),
        },
    )
    assert bad[0] == 400
    _, run = run_to_end(client, ws, interpreter=sys.executable)
    assert run["state"] == "finished"


@pytest.mark.skipif(
    sys.platform == "win32", reason="the fake interpreter is a shell script"
)
def test_too_old_interpreter_is_reported_not_hidden(client, tmp_path):
    fake = tmp_path / "python"
    fake.write_text(
        "#!/bin/sh\necho 'Concurim needs Python 3.13+' >&2\nexit 1\n"
    )
    fake.chmod(0o755)
    ws = client.upload({"main.py": "print('hi')\n"})
    _, run = run_to_end(client, ws, interpreter=str(fake))
    assert run["state"] == "failed" and "3.13" in run["output"]
    assert run["trace_ready"] is False


@pytest.mark.parametrize(
    "body",
    [
        {"workspace_id": "nope", "entry": "main.py"},
        {"script_path": "/etc/hosts"},
        {"script_path": "relative/missing.py"},
        {"script_path": ""},
        {},
    ],
)
def test_invalid_plans_are_400(client, body):
    assert client.post_json("/api/runs/plan", body)[0] == 400


def test_invalid_plan_options_are_400(client):
    ws = client.upload({"main.py": "pass\n"})
    for extra in ({"auto": "everything"}, {"args": "'unterminated"}):
        body = {"workspace_id": ws["id"], "entry": "main.py", **extra}
        assert client.post_json("/api/runs/plan", body)[0] == 400


@pytest.mark.parametrize(
    "path",
    [
        "../evil.py",
        "/abs/evil.py",
        "a/../../evil.py",
        "C:evil.py",
        "",
        "a//..",
        "x\x00.py",
    ],
)
def test_uploads_cannot_escape_their_workspace(client, tmp_path, path):
    import base64

    files = [{"path": path, "data": base64.b64encode(b"x=1").decode()}]
    status, body = client.post_json("/api/workspaces", {"files": files})
    assert status == 400, body
    assert not (tmp_path / "evil.py").exists()
    assert not Path("/abs/evil.py").exists()


def test_workspace_rejects_bad_payloads(client):
    for payload in (
        {"files": []},
        {"files": "x"},
        {"files": [{"path": "a.py", "data": "!!!"}]},
        {"files": [{"path": "notes.txt", "data": ""}]},
    ):
        assert client.post_json("/api/workspaces", payload)[0] == 400


def test_folder_upload_suggests_an_entry_point(client):
    ws = client.upload(
        {
            "pkg/__init__.py": "",
            "pkg/util.py": "def f(): pass\n",
            "main.py": "if __name__ == '__main__':\n    pass\n",
            "data/readme.txt": "hello",
        }
    )
    assert ws["suggested"] == "main.py"
    assert ws["entries"] == ["main.py"]
    assert "pkg/util.py" in ws["python_files"]


def test_scratch_files_are_removed_when_the_server_stops(tmp_path):
    server = serve(tmp_path)
    c = Client(server)
    c.upload({"main.py": "pass\n"})
    root = server.workspaces.root
    assert root.exists()
    stop(server)
    assert not root.exists()
