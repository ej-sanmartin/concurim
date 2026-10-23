"""Stable logical identities for threads, resources, and objects.

Raw ``threading.get_ident()`` values are reused by the OS, so traces use
logical ids such as ``thread-2`` instead.
"""

from __future__ import annotations

import itertools
import threading
from collections import defaultdict


class IdentityRegistry:
    """Allocates logical ids. All methods are thread-safe and non-blocking
    beyond one short, never-nested lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, itertools.count[int]] = defaultdict(
            lambda: itertools.count(1)
        )

    def new_id(self, prefix: str) -> str:
        """Return the next id for ``prefix`` (``thread-1``, ``queue-2``)."""
        with self._lock:
            return f"{prefix}-{next(self._counters[prefix])}"
