"""Functions run by worker processes (they must be importable by name)."""

import os
import time

GREETING = "unset"


def square(n):
    return n * n


def boom(n):
    raise ValueError(f"bad {n}")


def set_greeting(text):
    global GREETING
    GREETING = text


def greeting(_):
    return GREETING


def pid(_):
    return os.getpid()


def slow(seconds):
    """Busy for ``seconds``, so a line sampler has something to see."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass


def add(a, b):
    return a + b


def append_one(items):
    """Mutates its (copied) argument and reports the new length."""
    items.append(1)
    return len(items)


def bump(counter, items):
    """A process target: change a shared value and a copied list."""
    with counter.get_lock():
        counter.value += 1
    items.append(1)
