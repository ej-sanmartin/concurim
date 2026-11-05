"""A shared value whose reads and writes are recorded.

``TracedCell`` holds one Python value. Each ``cell.value`` read and each
assignment is one event, so ``cell.value += 1`` is a read and then a write,
which is exactly where a lost update can slip in. The replay shows the value
over time and which locks the reader or writer held at that moment.

The value is previewed only when previews are on (the same switch as queue
payloads), and only for plain built-in types.
"""

from __future__ import annotations

from typing import Any

from concurim.recorder.collector import Recorder, mark_internal
from concurim.recorder.events import EventType as E
from concurim.recorder.lifecycle import active_recorder

mark_internal(__file__)


def value_meta(rec: Recorder, value: Any) -> dict[str, Any]:
    """``value_type`` and (if allowed) ``preview`` metadata for ``value``."""
    info = rec.describe_payload(value)
    meta: dict[str, Any] = {"value_type": info["type"]}
    if "preview" in info:
        meta["preview"] = info["preview"]
    return meta


class TracedCell:
    """A value shared between threads or tasks, with every access recorded.

    Args:
        value: The initial value.
        name: Display name in the viewer.
    """

    def __init__(self, value: Any = None, *, name: str | None = None) -> None:
        self._value = value
        self._cz_name = name
        rec = active_recorder()
        if rec is not None:
            self._cz_rid(rec)

    def _cz_rid(self, rec: Recorder) -> str:
        return rec.resource_id(
            self, "cell", self._cz_name, value_meta(rec, self._value)
        )

    def _cz_emit(self, rec: Recorder, kind: str, value: Any) -> None:
        rec.emit(
            kind,
            resource_id=self._cz_rid(rec),
            source=rec.capture_source(),
            metadata=value_meta(rec, value),
        )

    @property
    def value(self) -> Any:
        """The current value; reading it is recorded."""
        value = self._value
        rec = active_recorder()
        if rec is not None:
            self._cz_emit(rec, E.CELL_READ, value)
        return value

    @value.setter
    def value(self, new: Any) -> None:
        self._value = new
        rec = active_recorder()
        if rec is not None:
            self._cz_emit(rec, E.CELL_WRITE, new)

    def get(self) -> Any:
        """Same as reading ``value``."""
        return self.value

    def set(self, new: Any) -> None:
        """Same as assigning ``value``."""
        self.value = new
