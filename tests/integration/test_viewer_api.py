"""Viewer API: samples, trace upload, and protection of mutating routes."""

from urllib.parse import quote

import pytest
from viewer_client import Client, serve, stop

from concurim.samples import SAMPLES_DIR, load_manifest


@pytest.fixture
def client(tmp_path):
    server = serve(tmp_path)
    yield Client(server)
    stop(server)


def test_home_state_has_no_trace_and_lists_samples_and_interpreters(client):
    session = client.get_json("/api/session")
    assert session["has_trace"] is False
    ids = [s["id"] for s in session["samples"]]
    assert ids == [s["id"] for s in load_manifest()["samples"]]
    assert session["planned"], "unsupported examples must be listed as planned"
    assert any(i["supported"] for i in session["interpreters"])
    assert client.request("GET", "/api/replay")[0] == 404


def test_index_html_receives_the_token_but_it_is_never_in_the_api(client):
    _, html, _ = client.request("GET", "/")
    assert client.server.token.encode() in html
    _, session, _ = client.request("GET", "/api/session")
    assert client.server.token.encode() not in session


@pytest.mark.parametrize(
    "sample", load_manifest()["samples"], ids=lambda s: s["id"]
)
def test_every_bundled_sample_opens_and_replays_cleanly(client, sample):
    status, _ = client.post_json(f"/api/samples/{sample['id']}/open")
    assert status == 200
    replay = client.get_json("/api/replay")
    assert replay["warnings"] == []
    assert replay["summary"]["event_count"] > 10
    shown = client.get_json("/api/session")
    assert shown["has_trace"] and shown["label"] == sample["title"]
    status, text, _ = client.request(
        "GET", f"/api/samples/{sample['id']}/source"
    )
    assert status == 200
    assert text.decode() == (SAMPLES_DIR / sample["source"]).read_text()


def test_samples_show_different_observability_for_the_same_program(client):
    def entities(sample_id):
        client.post_json(f"/api/samples/{sample_id}/open")
        return client.get_json("/api/replay")["entities"]

    threads_only = entities("plain-threads")
    with_queues = entities("plain-queues")
    assert len(threads_only["threads"]) == len(with_queues["threads"]) >= 4
    assert threads_only["queues"] == {}  # not observed: not invented
    assert len(with_queues["queues"]) == 1


def test_unknown_sample_is_404(client):
    assert client.post_json("/api/samples/nope/open")[0] == 404
    assert client.request("GET", "/api/samples/..%2f..%2fx/source")[0] == 404


def test_posts_need_the_token_and_a_local_origin(client):
    path = "/api/samples/producer-consumer/open"
    assert client.post_json(path, token=None)[0] == 403
    assert client.post_json(path, token="wrong")[0] == 403
    evil = client.post_json(path, origin="https://evil.example")
    assert evil[0] == 403
    port = client.server.server_address[1]
    assert client.post_json(path, origin=f"http://127.0.0.1:{port}")[0] == 200


def test_foreign_host_header_is_rejected_for_posts_too(client):
    status, _, _ = client.request(
        "POST", "/api/samples/shutdown/open", host="evil.example:80"
    )
    assert status == 403


def test_uploaded_trace_replaces_the_current_one(client):
    client.post_json("/api/samples/producer-consumer/open")
    before = client.get_json("/api/replay")["summary"]["event_count"]
    raw = (SAMPLES_DIR / "shutdown.concurim").read_bytes()
    status, _ = client.post_json("/api/trace?name=my.concurim", raw)
    assert status == 200
    assert client.get_json("/api/session")["label"] == "my.concurim"
    assert client.get_json("/api/replay")["summary"]["event_count"] != before


def test_bad_uploads_are_rejected_and_keep_the_current_trace(client):
    client.post_json("/api/samples/shutdown/open")
    for junk in (b"not a zip", b"", b"PK\x03\x04broken"):
        status, body = client.post_json("/api/trace", junk)
        assert status == 400 and "error" in body
    assert (
        client.get_json("/api/session")["label"] == "Cancellation and shutdown"
    )


def test_label_cannot_inject_markup_or_paths(client):
    raw = (SAMPLES_DIR / "shutdown.concurim").read_bytes()
    name = quote("<img src=x onerror=1>/../a")
    client.post_json(f"/api/trace?name={name}", raw)
    label = client.get_json("/api/session")["label"]
    assert "<" not in label and "/" not in label


def test_oversized_bodies_are_refused_before_reading(client):
    status, body = client.post_json(
        "/api/runs/plan", b"{}", content_length=10 * 1024 * 1024
    )
    assert status == 413


def test_source_endpoint_serves_only_loaded_sources(client):
    client.post_json("/api/samples/backpressure/open")
    assert client.request("GET", "/api/source?path=backpressure.py")[0] == 200
    for path in ("/etc/passwd", "../pyproject.toml", "backpressure.concurim"):
        assert client.request("GET", f"/api/source?path={path}")[0] == 404


def test_every_response_carries_security_headers(client):
    _, _, headers = client.request("GET", "/api/session")
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_two_recordings_can_be_loaded_for_comparison_without_the_session(
    client,
):
    assert client.get_json("/api/session")["compare"] == {"a": None, "b": None}
    assert client.request("GET", "/api/compare/a/replay")[0] == 404
    for slot, name in (("a", "shutdown"), ("b", "semaphore")):
        raw = (SAMPLES_DIR / f"{name}.concurim").read_bytes()
        status, _ = client.post_json(
            f"/api/compare/{slot}/trace?name={name}", raw
        )
        assert status == 200
    shown = client.get_json("/api/session")
    assert shown["compare"] == {"a": "shutdown", "b": "semaphore"}
    assert shown["has_trace"] is False  # the main viewer is untouched
    first = client.get_json("/api/compare/a/replay")
    second = client.get_json("/api/compare/b/replay")
    assert first["summary"]["event_count"] != second["summary"]["event_count"]
    assert first["metadata"]["environment"]["python_version"]


def test_compare_uploads_need_the_token_and_reject_junk_and_other_slots(client):
    raw = (SAMPLES_DIR / "shutdown.concurim").read_bytes()
    path = "/api/compare/a/trace?name=x"
    assert client.post_json(path, raw, token=None)[0] == 403
    assert client.post_json(path, b"not a zip")[0] == 400
    assert client.post_json("/api/compare/c/trace", raw)[0] == 404
