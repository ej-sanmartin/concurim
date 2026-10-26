"""The description of a run, shown before anything executes."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
BOOT_LABEL = "<concurim bootstrap>"


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
