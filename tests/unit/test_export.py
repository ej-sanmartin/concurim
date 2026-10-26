import sys

import pytest

from concurim.export import sink, video
from concurim.export.cdp import BROWSER_ENV, ExportError, find_browser
from concurim.export.cli import _parse_events
from concurim.export.options import (
    ExportOptions,
    options_from_request,
    parse_size,
)
from concurim.export.video import export_video
from concurim.recorder.serialization import load_trace
from concurim.samples import sample_file

TRACE = sample_file("cpu-threads.concurim")


def test_size_and_event_parsing():
    assert parse_size("1080p") == (1920, 1080)
    assert parse_size("640x360") == (640, 360)
    assert _parse_events(None) == (1, None)
    assert _parse_events("5:40") == (5, 40)
    assert _parse_events("7") == (7, None)
    with pytest.raises(ValueError):
        parse_size("huge")
    with pytest.raises(ValueError):
        _parse_events("a:b")


def test_footer_names_the_recording_range_and_hash():
    text = video._footer("run.concurim", 5, 9, 31, "abcdef0123456789")
    assert text == "run.concurim · events 5-9 of 31 · sha256 abcdef012345"


def test_missing_tools_give_actionable_errors(monkeypatch):
    monkeypatch.setenv(BROWSER_ENV, "/nonexistent/browser")
    with pytest.raises(ExportError, match=BROWSER_ENV):
        find_browser()
    monkeypatch.setattr(sink.shutil, "which", lambda _name: None)
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", None)
    with pytest.raises(ExportError, match=r"concurim\[video\]"):
        sink.find_ffmpeg()


def test_options_reject_out_of_range_values():
    for bad in ({"fps": 0}, {"hold": 0}, {"motion_ms": 99999},
                {"width": 10}, {"view": "nope"}, {"theme": "red"},
                {"overlays": ["nope"]}, {"start": 0}):  # fmt: skip
        with pytest.raises(ExportError):
            ExportOptions(**bad)


def test_web_request_is_validated_and_defaults_apply():
    options, fmt = options_from_request({})
    assert (fmt, options.view, options.motion_ms) == ("mp4", "animation", 400)
    options, fmt = options_from_request(
        {"format": "gif", "size": "square", "end": 9, "overlays": []}
    )
    assert (fmt, options.width, options.end, options.overlays) == (
        "gif", 1080, 9, ()
    )  # fmt: skip
    for bad in ({"format": "avi"}, {"size": "x"}, {"fps": "fast"},
                {"hold": None}):  # fmt: skip
        with pytest.raises(ExportError):
            options_from_request(bad)


def test_frame_schedule_never_glides_longer_than_the_hold():
    total, glide = video._frames_per_event(
        ExportOptions(fps=30, hold=1.0, motion_ms=400)
    )
    assert (total, glide) == (30, 12)
    total, glide = video._frames_per_event(
        ExportOptions(fps=30, hold=0.2, motion_ms=2000)
    )
    assert glide == total - 1


def test_rejects_unknown_output_and_bad_range(tmp_path):
    trace = load_trace(TRACE)
    with pytest.raises(ExportError, match="unsupported output"):
        export_video(trace, "t", tmp_path / "clip.avi", ExportOptions())
    with pytest.raises(ExportError, match="events must satisfy"):
        export_video(trace, "t", tmp_path / "frames", ExportOptions(start=999))


def _browser_or_skip():
    try:
        find_browser()
    except ExportError:
        pytest.skip("no Chrome-family browser installed")


def test_png_frames_are_identical_between_runs(tmp_path):
    """The headline promise: the same trace renders the same pixels."""
    _browser_or_skip()
    trace = load_trace(TRACE)
    options = ExportOptions(
        start=3, end=4, width=800, height=450, fps=10, hold=1, motion_ms=500
    )
    for name in ("one", "two"):
        assert export_video(trace, "t", tmp_path / name, options) == 2
    one = sorted((tmp_path / "one").glob("*.png"))
    assert len(one) == 20  # two events x (5 glide + 5 hold) frames
    for frame in one:
        assert (
            frame.read_bytes() == (tmp_path / "two" / frame.name).read_bytes()
        )
    # The second event glides: frames differ until it settles.
    shots = {p.read_bytes() for p in one}
    assert 3 <= len(shots) <= 8


def test_zero_motion_cuts_straight_between_events(tmp_path):
    _browser_or_skip()
    options = ExportOptions(
        start=3, end=4, width=800, height=450, fps=10, hold=1, motion_ms=0
    )
    export_video(load_trace(TRACE), "t", tmp_path / "cut", options)
    shots = {p.read_bytes() for p in (tmp_path / "cut").glob("*.png")}
    assert len(shots) == 2
