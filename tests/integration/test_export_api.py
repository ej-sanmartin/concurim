"""Export from the web UI: validation, protection, and a real download."""

import io
import time
import zipfile

import pytest
from viewer_client import Client, serve, stop

from concurim.export.cdp import ExportError, find_browser
from concurim.recorder.serialization import load_trace
from concurim.samples import sample_file


@pytest.fixture
def client(tmp_path):
    server = serve(tmp_path, load_trace(sample_file("cpu-threads.concurim")))
    yield Client(server)
    stop(server)


def wait_export(client, job_id, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get_json(f"/api/export/{job_id}")
        if job["state"] != "running":
            return job
        time.sleep(0.1)
    raise AssertionError("export did not finish in time")


def test_session_reports_what_this_machine_can_export(client):
    caps = client.get_json("/api/session")["export"]
    assert {"browser", "ffmpeg", "problems", "formats"} <= set(caps)
    assert caps["formats"] == ["mp4", "webm", "gif", "png"]
    for key in ("browser", "ffmpeg"):
        assert caps[key] or key in caps["problems"]


def test_export_needs_the_token_and_validates_options(client):
    assert client.post_json("/api/export", {}, token=None)[0] == 403
    for bad in ({"format": "avi"}, {"fps": 999}, {"view": "../x"},
                {"start": 500}):  # fmt: skip
        status, body = client.post_json("/api/export", bad)
        assert status == 400 and body["error"], bad
    assert client.request("GET", "/api/export/nope")[0] == 404
    assert client.post_json("/api/export/nope/cancel")[0] == 404


def test_export_without_a_recording_is_a_clear_error(tmp_path):
    server = serve(tmp_path)
    try:
        status, body = Client(server).post_json("/api/export", {})
    finally:
        stop(server)
    assert status == 400 and "no recording" in body["error"]


def test_png_export_downloads_as_a_zip_of_frames(client):
    try:
        find_browser()
    except ExportError:
        pytest.skip("no Chrome-family browser installed")
    status, job = client.post_json(
        "/api/export",
        {"format": "png", "start": 3, "end": 4, "size": "640x360",
         "fps": 10, "hold": 1, "motion_ms": 0},
    )  # fmt: skip
    assert status == 202 and job["state"] == "running"
    assert client.request("GET", f"/api/export/{job['id']}/file")[0] == 404
    done = wait_export(client, job["id"])
    assert done["state"] == "done", done
    status, data, headers = client.request(
        "GET", f"/api/export/{job['id']}/file"
    )
    assert status == 200 and headers["Content-Type"] == "application/zip"
    assert 'filename="' in headers["Content-Disposition"]
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert len(names) == 20 and names[0] == "frame-00001.png"


def test_a_second_export_is_refused_while_one_runs_and_cancel_works(client):
    try:
        find_browser()
    except ExportError:
        pytest.skip("no Chrome-family browser installed")
    _, job = client.post_json("/api/export", {"format": "png"})
    status, body = client.post_json("/api/export", {"format": "png"})
    assert status == 409 and "already" in body["error"]
    client.post_json(f"/api/export/{job['id']}/cancel")
    assert wait_export(client, job["id"])["state"] == "cancelled"
