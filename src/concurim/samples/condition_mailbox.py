"""threading.Condition: a mailbox that wakes sleeping readers.

No Concurim imports. Two readers wait on a condition until a message is
posted. ``notify()`` does not release the lock: the poster keeps it until it
leaves the ``with`` block, and a woken reader must then re-acquire it before
it can read.
"""

import threading
import time

mailbox: list[str] = []
changed = threading.Condition()


def reader() -> None:
    """Sleep until a message arrives, then take it."""
    with changed:
        while not mailbox:
            changed.wait()
        mailbox.pop(0)


def post(message: str) -> None:
    """Add a message and wake one waiting reader."""
    with changed:
        mailbox.append(message)
        changed.notify()
        time.sleep(0.03)  # still holding the lock: nobody can read yet


def main() -> None:
    readers = [
        threading.Thread(target=reader, name=f"reader-{i}") for i in (1, 2)
    ]
    for thread in readers:
        thread.start()
    time.sleep(0.1)  # both readers are waiting
    post("first")
    time.sleep(0.05)
    post("second")
    for thread in readers:
        thread.join()


if __name__ == "__main__":
    main()
