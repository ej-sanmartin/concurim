"""Functions run by worker processes (they must be importable by name)."""

import os

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
