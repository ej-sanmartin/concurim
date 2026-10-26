import sys

import pytest

from concurim.cli import _parse_events, _parse_size
from concurim.export import video
from concurim.export.cdp import BROWSER_ENV, ExportError, find_browser
from concurim.export.video import ExportOptions, export_video
from concurim.samples import sample_file


def test_size_and_event_parsing():
    assert _parse_size("1080p") == (1920, 1080)
    assert _parse_size("640x360") == (640, 360)
    assert _parse_events(None) == (1, None)
    assert _parse_events("5:40") == (5, 40)
    assert _parse_events("7") == (7, None)
    with pytest.raises(ValueError):
        _parse_size("huge")
    with pytest.raises(ValueError):
        _parse_events("a:b")


def test_footer_names_the_recording_range_and_hash():
    text = video._footer("run.concurim", 5, 9, 31, "abcdef0123456789")
    assert text == "run.concurim · events 5-9 of 31 · sha256 abcdef012345"


def test_missing_tools_give_actionable_errors(monkeypatch):
    monkeypatch.setenv(BROWSER_ENV, "/nonexistent/browser")
    with pytest.raises(ExportError, match=BROWSER_ENV):
        find_browser()
    monkeypatch.setattr(video.shutil, "which", lambda _name: None)
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", None)
    with pytest.raises(ExportError, match=r"concurim\[video\]"):
        video.find_ffmpeg()


def test_rejects_unknown_output_and_bad_range(tmp_path):
    trace = sample_file("cpu-threads.concurim")
    with pytest.raises(ExportError, match="unsupported output"):
        export_video(trace, tmp_path / "clip.avi", ExportOptions())
    with pytest.raises(ExportError, match="events must satisfy"):
        export_video(trace, tmp_path / "frames", ExportOptions(start=999))


def test_png_frames_are_identical_between_runs(tmp_path):
    """The headline promise: the same trace renders the same pixels."""
    try:
        find_browser()
    except ExportError:
        pytest.skip("no Chrome-family browser installed")
    trace = sample_file("cpu-threads.concurim")
    options = ExportOptions(start=3, end=4, width=800, height=450)
    for name in ("one", "two"):
        assert export_video(trace, tmp_path / name, options) == 2
    for frame in ("frame-00001.png", "frame-00002.png"):
        first = (tmp_path / "one" / frame).read_bytes()
        assert first == (tmp_path / "two" / frame).read_bytes()
    first_png = (tmp_path / "one" / "frame-00001.png").read_bytes()
    assert first_png != (tmp_path / "one" / "frame-00002.png").read_bytes()
