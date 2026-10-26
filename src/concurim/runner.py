"""Run a user script under a recording, preserving its behavior."""

from __future__ import annotations

import runpy
import sys
import threading
import traceback
from pathlib import Path

from concurim.config import RecorderConfig
from concurim.program_check import check_script
from concurim.recorder.lifecycle import record


def run_recorded(
    script: Path,
    args: list[str],
    output: Path,
    config: RecorderConfig,
    *,
    view_on_stop: bool = False,
) -> tuple[int, int]:
    """Execute ``script`` as ``__main__`` and write the trace to ``output``.

    Command-line arguments, the working directory, exceptions (printed as
    usual) and the exit status are preserved. Like a normal interpreter
    exit, this waits for the script's non-daemon threads before finishing.
    A script that does not compile is refused before it starts. On
    interrupt, threads that are still blocked are not joined: joining them
    would hang, and the trace is written from the ``record`` block instead.

    Args:
        script: Entry point to run as ``__main__``.
        args: Arguments after the script path, passed through unchanged.
        output: Where to write the ``.concurim`` trace.
        config: Recorder settings for this run.
        view_on_stop: When true and the process has to exit because threads
            are stuck, start ``concurim view`` on the trace first.

    Returns:
        ``(exit_code, event_count)``.
    """
    check_script(script)
    old_argv, old_path = sys.argv, list(sys.path)
    sys.argv = [str(script), *args]
    sys.path.insert(0, str(script.resolve().parent))
    ctx = record(output, config=config, program={"script": script.name})
    ctx.view_on_stop = view_on_stop
    code = 0
    try:
        with ctx as recorder:
            try:
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit as exit_:
                code = _exit_code(exit_)
            except KeyboardInterrupt:
                code, ctx.program["exception"] = 130, "KeyboardInterrupt"
                ctx.program["outcome"] = "interrupted"
            except BaseException as error:
                traceback.print_exc()
                code, ctx.program["exception"] = 1, type(error).__name__
            if code != 130:
                try:
                    _join_non_daemon_threads()
                except KeyboardInterrupt:
                    code = 130
                    ctx.program["exception"] = "KeyboardInterrupt"
                    ctx.program["outcome"] = "interrupted"
            ctx.program["exit_code"] = code
            count = len(recorder.events())
    finally:
        sys.argv, sys.path[:] = old_argv, old_path
    return code, count


def _exit_code(exc: SystemExit) -> int:
    if exc.code is None:
        return 0
    if isinstance(exc.code, int):
        return exc.code
    print(exc.code, file=sys.stderr)
    return 1


def _join_non_daemon_threads() -> None:
    current = threading.current_thread()
    for thread in threading.enumerate():
        if thread is not current and not thread.daemon:
            thread.join()
