"""Programs that cannot start are refused before they run."""

from pathlib import Path

import pytest

from concurim.program_check import ProgramError, check_script


def test_a_syntax_error_is_refused(tmp_path: Path):
    path = tmp_path / "bad.py"
    path.write_text("def (\n")
    with pytest.raises(ProgramError, match="cannot run"):
        check_script(path)


def test_an_indentation_error_is_refused(tmp_path: Path):
    path = tmp_path / "bad.py"
    path.write_text("def f():\nprint(1)\n")
    with pytest.raises(ProgramError, match="IndentationError"):
        check_script(path)


def test_a_null_byte_is_refused(tmp_path: Path):
    path = tmp_path / "bad.py"
    path.write_bytes(b"print(1)\n\0")
    with pytest.raises(ProgramError, match="cannot run"):
        check_script(path)


def test_a_compiling_file_is_accepted(tmp_path: Path):
    path = tmp_path / "ok.py"
    path.write_text("print(1)\n")
    check_script(path)
