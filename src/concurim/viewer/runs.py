"""Plan, confirm, run and cancel a recorded program.

Nothing executes until ``start`` is called for a plan the user confirmed.
The plan is built by the server, so the UI shows exactly what will run.
The program runs with this process's permissions; there is no sandbox.
"""

from __future__ import annotations

import io
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import concurim
from concurim.instrumentation.auto import LEVELS
from concurim.recorder.serialization import Trace, load_trace
from concurim.viewer.procs import escalate, kill_now, spawn
from concurim.viewer.workspaces import Workspaces

# Runs in the *target* interpreter, which may not have Concurim installed:
# a private copy of the (pure Python) package is appended to sys.path.
BOOT = (
    "import sys\n"
    "if sys.version_info < (3, 13):\n"
    "    sys.exit('Concurim needs Python 3.13+; this is '"
    " + sys.version.split()[0])\n"
    "sys.path.append(sys.argv.pop(1))\n"
    "from concurim.cli import main\n"
    "sys.exit(main())\n"
)
MAX_OUTPUT = 256 * 1024
MAX_PLANS = 32


class RunError(ValueError):
    """The request was invalid (reported to the UI as HTTP 400)."""


class RunConflict(RuntimeError):
    """Another program is already running (HTTP 409)."""


@dataclass
class Plan:
    """Everything that will happen if the user confirms."""

    id: str
    argv: list[str]
    cwd: str
    script: str
    args: list[str]
    interpreter: str
    auto: str
    include_source: bool
    preview: bool
    trace_path: Path

    def describe(self) -> dict[str, Any]:
        """JSON-ready description shown to the user before running."""
        shown = [BOOT_LABEL if a == BOOT else a for a in self.argv]
        return {
            "id": self.id,
            "interpreter": self.interpreter,
            "script": self.script,
            "args": self.args,
            "cwd": self.cwd,
            "auto": self.auto,
            "include_source": self.include_source,
            "preview": self.preview,
            "command": shlex.join(shown),
        }


BOOT_LABEL = "<concurim bootstrap>"


@dataclass
class Run:
    """A started program."""

    plan: Plan
    proc: subprocess.Popen[bytes] | None = None
    state: str = "running"
    exit_code: int | None = None
    output: bytearray = field(default_factory=bytearray)
    truncated: bool = False
    trace_ready: bool = False
    exception: str | None = None
    error: str | None = None
    cancelled: bool = False

    def status(self) -> dict[str, Any]:
        """JSON-ready snapshot."""
        return {
            "id": self.plan.id,
            "state": self.state,
            "exit_code": self.exit_code,
            "output": bytes(self.output).decode("utf-8", "replace"),
            "output_truncated": self.truncated,
            "trace_ready": self.trace_ready,
            "exception": self.exception,
            "error": self.error,
            "script": self.plan.script,
        }


class RunManager:
    """Owns plans and at most one running program."""

    def __init__(
        self,
        workspaces: Workspaces,
        on_trace: Callable[[Trace, str], None],
    ) -> None:
        self.workspaces = workspaces
        self._on_trace = on_trace
        self._lock = threading.Lock()
        self._plans: OrderedDict[str, Plan] = OrderedDict()
        self._runs: dict[str, Run] = {}
        self._boot: Path | None = None

    # -- planning ----------------------------------------------------------

    def plan(self, req: dict[str, Any]) -> dict[str, Any]:
        """Validate a request and describe (not execute) the run."""
        cwd, script = self._locate(req)
        interpreter = _interpreter(req.get("interpreter"))
        auto = req.get("auto", "threads")
        if auto not in LEVELS:
            raise RunError("unknown instrumentation level")
        try:
            args = shlex.split(str(req.get("args") or ""))
        except ValueError as exc:
            raise RunError(f"cannot parse arguments: {exc}") from exc
        if len(args) > 100 or any(len(a) > 2000 for a in args):
            raise RunError("too many or too long arguments")
        plan_id = secrets.token_hex(8)
        trace_path = self.workspaces.root / "runs" / plan_id / "trace.concurim"
        include_source = bool(req.get("include_source"))
        preview = bool(req.get("preview"))
        argv = [interpreter, "-c", BOOT, str(self._boot_dir()), "record"]
        argv += ["--auto", auto, "-o", str(trace_path)]
        argv += ["--include-source"] * include_source
        argv += ["--preview"] * preview
        argv += [str(script), *args]
        plan = Plan(
            plan_id,
            argv,
            str(cwd),
            str(script),
            args,
            interpreter,
            auto,
            include_source,
            preview,
            trace_path,
        )
        with self._lock:
            self._plans[plan_id] = plan
            while len(self._plans) > MAX_PLANS:
                self._plans.popitem(last=False)
        return plan.describe()

    def _locate(self, req: dict[str, Any]) -> tuple[Path, Path]:
        if req.get("workspace_id"):
            return self.workspaces.resolve(
                req["workspace_id"], req.get("entry")
            )
        raw = req.get("script_path")
        if not isinstance(raw, str) or not raw or len(raw) > 1000:
            raise RunError("choose a Python file to run")
        script = Path(raw).expanduser().resolve()
        if script.suffix != ".py" or not script.is_file():
            raise RunError(f"not a .py file: {script}")
        return script.parent, script

    def _boot_dir(self) -> Path:
        """A directory holding only a copy of the ``concurim`` package."""
        if self._boot is None:
            dest = self.workspaces.root / "boot"
            shutil.copytree(
                Path(concurim.__file__).parent,
                dest / "concurim",
                ignore=shutil.ignore_patterns(
                    "viewer", "samples", "__pycache__", "*.pyc"
                ),
            )
            self._boot = dest
        return self._boot

    # -- running -----------------------------------------------------------

    def start(self, plan_id: str) -> dict[str, Any]:
        """Execute a previously planned run (call only after confirmation)."""
        with self._lock:
            if any(r.state == "running" for r in self._runs.values()):
                raise RunConflict("a program is already running")
            plan = self._plans.pop(plan_id, None)
            if plan is None:
                raise RunError("unknown or expired plan")
            run = Run(plan)
            self._runs[plan_id] = run
        plan.trace_path.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        try:
            run.proc = spawn(plan.argv, cwd=plan.cwd, env=env)
        except OSError as exc:
            run.state, run.error = "error", f"could not start: {exc}"
            return run.status()
        threading.Thread(target=self._pump, args=(run,), daemon=True).start()
        return run.status()

    def _pump(self, run: Run) -> None:
        proc = run.proc
        assert proc is not None and proc.stdout is not None
        stream = cast(io.BufferedReader, proc.stdout)
        while chunk := stream.read1(4096):
            run.output += chunk
            if len(run.output) > MAX_OUTPUT:
                del run.output[: len(run.output) - MAX_OUTPUT]
                run.truncated = True
        code = proc.wait()
        self._finish(run, code)

    def _finish(self, run: Run, code: int) -> None:
        run.exit_code = code
        path = run.plan.trace_path
        if path.is_file():
            try:
                trace = load_trace(path)
                program = trace.metadata.get("program", {})
                run.exception = program.get("exception")
                self._on_trace(trace, Path(run.plan.script).name)
                run.trace_ready = True
            except (OSError, ValueError) as exc:
                run.error = f"the recording could not be opened: {exc}"
        run.state = (
            "cancelled"
            if run.cancelled
            else "finished"
            if code == 0
            else "failed"
        )

    def status(self, run_id: str) -> dict[str, Any]:
        """Current state of a run."""
        run = self._runs.get(run_id)
        if run is None:
            raise RunError("unknown run")
        return run.status()

    def cancel(self, run_id: str) -> dict[str, Any]:
        """Interrupt a running program (Ctrl-C first, then terminate/kill)."""
        run = self._runs.get(run_id)
        if run is None:
            raise RunError("unknown run")
        if run.state == "running" and run.proc and run.proc.poll() is None:
            run.cancelled = True
            threading.Thread(
                target=escalate, args=(run.proc,), daemon=True
            ).start()
        return run.status()

    def shutdown(self) -> None:
        """Stop any running program and delete scratch files."""
        for run in self._runs.values():
            if run.proc and run.proc.poll() is None:
                kill_now(run.proc)
        self.workspaces.cleanup()


def _interpreter(value: object) -> str:
    if value in (None, ""):
        return sys.executable
    if not isinstance(value, str) or len(value) > 1000:
        raise RunError("invalid interpreter")
    path = os.path.abspath(os.path.expanduser(value))
    if not os.path.isfile(path) or not os.access(path, os.X_OK):
        raise RunError(f"interpreter not found or not executable: {path}")
    return path
