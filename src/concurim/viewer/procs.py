"""Process-group control for recorded programs (POSIX and Windows).

POSIX: the program starts in its own session, so signals reach its whole
process group (threads, child processes). Windows: there are no process
groups to signal, so the program is only terminated; this branch is not
tested in CI yet.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time

GRACE_SECONDS = 3.0
_WINDOWS = os.name == "nt"


def spawn(
    argv: list[str], *, cwd: str, env: dict[str, str]
) -> subprocess.Popen[bytes]:
    """Start the program in its own group, merging stderr into stdout."""
    return subprocess.Popen(  # noqa: S603 - the user confirmed this run
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=not _WINDOWS,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )


def signal_group(proc: subprocess.Popen[bytes], sig: int) -> None:
    """Send ``sig`` to the program's process group (terminate on Windows)."""
    try:
        if _WINDOWS:
            proc.terminate()
        else:
            os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def kill_now(proc: subprocess.Popen[bytes]) -> None:
    """Force the program to stop and wait for it."""
    signal_group(proc, getattr(signal, "SIGKILL", signal.SIGTERM))
    proc.wait()


def escalate(proc: subprocess.Popen[bytes]) -> None:
    """Interrupt, then terminate, then kill, waiting a grace period each."""
    kill = getattr(signal, "SIGKILL", signal.SIGTERM)
    for sig in (signal.SIGINT, signal.SIGTERM, kill):
        signal_group(proc, sig)
        deadline = time.monotonic() + GRACE_SECONDS
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return
            time.sleep(0.05)
