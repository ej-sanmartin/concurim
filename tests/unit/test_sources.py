"""Source files embedded in a trace, including symlink paths."""

from concurim.config import RecorderConfig
from concurim.recorder.serialization import load_trace
from concurim.runner import run_recorded


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
