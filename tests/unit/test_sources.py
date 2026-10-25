"""Source files embedded in a trace, including symlink paths."""

import os
import sys

from concurim.config import RecorderConfig
from concurim.recorder.collector import Recorder
from concurim.recorder.sampler import _under_root
from concurim.recorder.serialization import load_trace
from concurim.runner import run_recorded


def test_a_file_on_another_drive_is_shown_as_is(tmp_path, monkeypatch):
    """Windows has no relative path between drives (``relpath`` raises)."""

    def other_drive(path, start=os.curdir):
        raise ValueError("path is on mount 'C:', start on mount 'D:'")

    monkeypatch.setattr(os.path, "relpath", other_drive)
    other = os.path.abspath(sys.executable)
    recorder = Recorder(RecorderConfig(source_root=str(tmp_path)))
    assert recorder.display_path(other) == other
    assert not _under_root(other, str(tmp_path))


def test_source_is_embedded_when_the_script_path_is_a_symlink(tmp_path):
    """``/tmp`` is a symlink on macOS; the resolved root must still match."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "app.py").write_text(
        "import threading\n"
        "def work():\n"
        "    pass\n"
        "threading.Thread(target=work).start()\n"
    )
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    out = tmp_path / "run.concurim"
    config = RecorderConfig(
        include_source=True,
        auto="threads",
        source_root=str((link / "app.py").resolve().parent),
    )
    run_recorded(link / "app.py", [], out, config)
    trace = load_trace(out)
    assert "app.py" in trace.sources
    assert "def work" in trace.sources["app.py"]
