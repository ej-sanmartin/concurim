"""Snapshots of a recording that may never return.

The trace is normally written when the ``record`` block ends. A deadlock
never ends: non-daemon threads stay blocked, so the process never reaches
that write. This guard flushes the buffer about once a second and, on
SIGINT or SIGTERM, writes immediately. If the main thread does not unwind,
the process exits after the write so a stuck join cannot swallow the file.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from typing import Any

from concurim.recorder.collector import mark_internal

# Created while automatic instrumentation is already on. These objects are
# the recorder's own plumbing, not part of the program being watched.
mark_internal(__file__)

_FLUSH_NAME = "concurim-flush"
# Long enough for a responsive Ctrl-C to save and return, short enough that
# a stuck main thread still produces a file before the parent kills us.
_EXIT_GRACE_S = 2.0


def still_blocked() -> bool:
    """True when a non-daemon thread other than main is still alive."""
    for thread in threading.enumerate():
        if not thread.is_alive() or thread.daemon:
            continue
        if thread is threading.main_thread() or thread.name == _FLUSH_NAME:
            continue
        return True
    return False


def _interval() -> float:
    """Seconds between snapshots (``CONCURIM_FLUSH_S``, default 1)."""
    raw = os.environ.get("CONCURIM_FLUSH_S", "")
    try:
        value = float(raw) if raw else 1.0
    except ValueError:
        return 1.0
    return min(max(value, 0.05), 60.0)


class FlushGuard:
    """Flush ``recording`` while it is active, and on SIGINT / SIGTERM.

    Installed only when the recording has a path to write, and only the
    main thread can install the signal handlers.
    """

    def __init__(self, recording: Any) -> None:
        self.recording = recording
        self._stop = threading.Event()
        self._signaled = threading.Event()
        self._signum = 0
        self._prev: dict[int, Any] = {}
        self._interval = _interval()
        self._thread = threading.Thread(
            target=self._loop, name=_FLUSH_NAME, daemon=True
        )

    def start(self) -> None:
        """Begin flushing and, on the main thread, catch stop signals."""
        # Import lazily: threads.py imports the recorder, which imports us.
        from concurim.instrumentation.threads import PLUMBING_FILES

        PLUMBING_FILES.add(__file__)
        self._thread.start()
        if threading.current_thread() is not threading.main_thread():
            return
        for sig in (signal.SIGINT, getattr(signal, "SIGTERM", None)):
            if sig is None:
                continue
            try:
                self._prev[sig] = signal.signal(sig, self._handle)
            except (ValueError, OSError):
                continue

    def stop(self) -> None:
        """Restore signals and wait for the flush thread to leave."""
        self._restore_signals()
        self.recording.stop_snapshots = True
        self._stop.set()
        self._signaled.set()  # wake the interval wait
        if self._thread.is_alive():
            self._thread.join(timeout=_EXIT_GRACE_S + 1)

    def _handle(self, signum: int, _frame: object) -> None:
        self._signum = signum
        self._signaled.set()
        if signum == signal.SIGINT:
            raise KeyboardInterrupt

    def _restore_signals(self) -> None:
        for sig, prev in self._prev.items():
            try:
                signal.signal(sig, prev)
            except (ValueError, OSError):
                continue
        self._prev.clear()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._signaled.wait(self._interval)
            if self._stop.is_set():
                return
            if self._signaled.is_set():
                self._signaled.clear()
                name = signal.Signals(self._signum).name if self._signum else ""
                self.recording.snapshot("interrupted", name)
                if self._stop.wait(_EXIT_GRACE_S):
                    return
                self._hard_exit()
                return
            self.recording.snapshot("running")

    def _hard_exit(self) -> None:
        """Leave without joining stuck threads, after the file is written."""
        path = self.recording.path
        print(
            "concurim: stopped while the program was still blocked; "
            f"wrote {path}",
            file=sys.stderr,
        )
        print(f"concurim: view it with: concurim view {path}", file=sys.stderr)
        if getattr(self.recording, "view_on_stop", False) and path is not None:
            subprocess.Popen(  # noqa: S603 - our own module, a new session
                [sys.executable, "-m", "concurim", "view", str(path)],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        code = 128 + (self._signum or signal.SIGTERM)
        os._exit(code)
