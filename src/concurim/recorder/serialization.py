"""Reading and writing ``.concurim`` trace files.

A trace is a zip archive with ``metadata.json``, ``events.jsonl`` and an
optional ``sources/`` directory. Members are only ever read into memory by
exact name; nothing is extracted to disk and nothing is unpickled.
"""

from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from concurim.recorder.events import SCHEMA_VERSION, Event, TraceFormatError

FORMAT_NAME = "concurim-trace"
FORMAT_VERSION = 1
MAX_EVENTS_BYTES = 512 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
MAX_SOURCE_BYTES = 1024 * 1024
MAX_SOURCES = 500
MAX_EVENTS = 5_000_000


@dataclass(slots=True)
class Trace:
    """A loaded recording."""

    metadata: dict[str, Any]
    events: list[Event]
    sources: dict[str, str] = field(default_factory=dict)


def write_trace(
    path: str | Path,
    metadata: dict[str, Any],
    events: list[Event],
    sources: dict[str, str],
) -> None:
    """Write a trace archive. ``sources`` maps display path -> file text."""
    meta = dict(metadata)
    meta.update(
        format=FORMAT_NAME,
        format_version=FORMAT_VERSION,
        schema_version=SCHEMA_VERSION,
    )
    members: dict[str, str] = {}
    index: dict[str, str] = {}
    for i, (name, text) in enumerate(sorted(sources.items())):
        member = f"sources/{i}.txt"
        members[member] = text
        index[name] = member
    meta["sources"] = index
    # Write aside and replace, so a reader never sees a half-written zip.
    # Snapshots of a live run land on the same path about once a second.
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("metadata.json", json.dumps(meta, indent=2))
            with zf.open("events.jsonl", "w") as out:
                for event in events:
                    line = json.dumps(event.to_dict(), separators=(",", ":"))
                    out.write(line.encode() + b"\n")
            for member, text in members.items():
                zf.writestr(member, text)
        os.replace(tmp, dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def load_trace(path: str | Path | BinaryIO) -> Trace:
    """Load and fully validate a trace. Raises ``TraceFormatError``."""
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise TraceFormatError(f"not a readable .concurim file: {exc}") from exc
    with zf:
        names = {i.filename: i for i in zf.infolist()}
        for required in ("metadata.json", "events.jsonl"):
            if required not in names:
                raise TraceFormatError(f"missing {required}")
        metadata = _read_metadata(zf, names["metadata.json"])
        events = _read_events(zf, names["events.jsonl"])
        sources = _read_sources(zf, names, metadata)
    return Trace(metadata, events, sources)


def _read_metadata(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo
) -> dict[str, Any]:
    if info.file_size > MAX_METADATA_BYTES:
        raise TraceFormatError("metadata.json too large")
    try:
        meta = json.loads(zf.read(info))
    except ValueError as exc:
        raise TraceFormatError(f"invalid metadata.json: {exc}") from exc
    if not isinstance(meta, dict) or meta.get("format") != FORMAT_NAME:
        raise TraceFormatError("not a concurim trace")
    if meta.get("format_version") != FORMAT_VERSION:
        raise TraceFormatError(
            f"unsupported format_version {meta.get('format_version')!r}"
        )
    return meta


def _read_events(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> list[Event]:
    if info.file_size > MAX_EVENTS_BYTES:
        raise TraceFormatError("events.jsonl too large")
    events: list[Event] = []
    last_seq: dict[int, int] = {}
    with zf.open(info) as handle:
        for line_no, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            if len(events) >= MAX_EVENTS:
                raise TraceFormatError("too many events")
            try:
                event = Event.from_dict(json.loads(raw))
            except (ValueError, TraceFormatError) as exc:
                raise TraceFormatError(
                    f"events.jsonl:{line_no}: {exc}"
                ) from exc
            if event.sequence <= last_seq.get(event.process_id, 0):
                raise TraceFormatError(
                    f"events.jsonl:{line_no}: sequence not increasing"
                )
            last_seq[event.process_id] = event.sequence
            events.append(event)
    return events


def _read_sources(
    zf: zipfile.ZipFile,
    names: dict[str, zipfile.ZipInfo],
    metadata: dict[str, Any],
) -> dict[str, str]:
    index = metadata.get("sources") or {}
    if not isinstance(index, dict) or len(index) > MAX_SOURCES:
        raise TraceFormatError("invalid sources index")
    sources: dict[str, str] = {}
    for name, member in index.items():
        info = names.get(member)
        if (
            not isinstance(name, str)
            or not isinstance(member, str)
            or info is None
            or not member.startswith("sources/")
        ):
            raise TraceFormatError(f"invalid source entry {name!r}")
        if info.file_size > MAX_SOURCE_BYTES:
            raise TraceFormatError(f"source too large: {name!r}")
        sources[name] = zf.read(info).decode("utf-8", errors="replace")
    return sources
