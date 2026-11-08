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


def locked_bump(lock, counter):
    """Add one to a shared value while holding an explicit lock."""
    with lock:
        counter.value += 1


def bump_value(counter):
    """Add one with no lock of our own (the value may have its own)."""
    counter.value += 1


def reenter(lock):
    """Take a reentrant lock twice."""
    with lock, lock:
        pass


def store(counter, number):
    """Set a shared value."""
    counter.value = number


def bump_together(counter, barrier):
    """Add one with no lock, then wait so both children overlap."""
    counter.value += 1
    barrier.wait()


def wait_for_event(event):
    """Block until the event is set (or fail after a generous timeout)."""
    assert event.wait(30)


def set_event(event):
    """Set the event."""
    event.set()


def meet(barrier):
    """Arrive at the barrier and wait for the other party."""
    barrier.wait(30)
