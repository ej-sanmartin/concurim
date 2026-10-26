"""Refuse programs that cannot start.

Concurim records a run, including one that fails after it has begun. A file
that does not compile never begins, so it is rejected before anything is
executed. Imported modules are not compiled here: that would mean running
the program.
"""

from __future__ import annotations

from pathlib import Path


class ProgramError(ValueError):
    """The program cannot be started (it does not compile)."""


def check_script(path: Path) -> None:
    """Raise ``ProgramError`` if ``path`` is not executable Python.

    The file is decoded the way CPython decodes a script (coding cookie
    included) and compiled. It is not imported and not run.

    Args:
        path: The entry-point file the user asked to record.

    Raises:
        ProgramError: The file cannot be read or compiled.
    """
    try:
        source = path.read_bytes()
    except OSError as exc:
        raise ProgramError(f"cannot read {path.name}: {exc}") from exc
    try:
        compile(source, str(path), "exec")
    except SyntaxError as exc:
        where = f" on line {exc.lineno}" if exc.lineno else ""
        detail = exc.msg or exc.__class__.__name__
        raise ProgramError(
            f"{path.name} cannot run ({exc.__class__.__name__}{where}: "
            f"{detail}). Concurim only records programs that start."
        ) from exc
    except ValueError as exc:
        raise ProgramError(
            f"{path.name} cannot run ({exc}). "
            "Concurim only records programs that start."
        ) from exc
