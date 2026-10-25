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
