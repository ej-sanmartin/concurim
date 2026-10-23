"""Shared helpers for the Concurim test-suite."""

from __future__ import annotations

import threading

import pytest

import concurim
from concurim.recorder.lifecycle import record

TIMEOUT = 10.0


@pytest.fixture
def rec():
    """An active in-memory recorder (no file written)."""
    with record() as recorder:
        yield recorder


def types(events, prefix=""):
    """Event types (optionally filtered by prefix) in recorded order."""
    return [e.event_type for e in events if e.event_type.startswith(prefix)]


def run_threads(*targets):
    """Start TracedThreads, join them with a deadlock-detecting timeout."""
    threads = [concurim.TracedThread(target=t) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(TIMEOUT)
        assert not t.is_alive(), "thread did not finish (possible deadlock)"
    return threads


def wait_for(predicate, timeout=TIMEOUT):
    """Poll until ``predicate()`` is true (for synchronizing test threads)."""
    done = threading.Event()
    deadline = timeout
    while deadline > 0 and not predicate():
        done.wait(0.005)
        deadline -= 0.005
    assert predicate(), "condition not reached in time"


def world_after(replay, i=None):
    """Fold replay frames into the state after event ``i`` (default: last)."""
    i = len(replay["frames"]) - 1 if i is None else i
    world = {"threads": {}, "queues": {}, "objects": {}}
    for frame in replay["frames"][: i + 1]:
        for kind, entities in frame["changes"].items():
            world[kind].update(entities)
    return world
