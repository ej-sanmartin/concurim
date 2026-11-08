"""Reentrant lock: one thread takes the same lock twice.

No Concurim imports. ``total()`` takes the lock and calls ``add()``, which
takes it again. A plain ``Lock`` would deadlock here; an ``RLock`` counts the
holds, so the thread goes two deep and must release twice. The second
thread waits until the first one is completely out.
"""

import threading
import time

lock = threading.RLock()
amount = 0


def add(n: int) -> None:
    """Add ``n``; takes the lock itself so it is safe to call alone."""
    global amount
    with lock:
        amount += n


def total(values: list[int]) -> None:
    """Add every value while holding the lock for the whole batch."""
    with lock:
        for n in values:
            add(n)  # re-enters the lock held by this same thread
            time.sleep(0.02)


def main() -> None:
    threads = [
        threading.Thread(target=total, args=([1, 2],), name="batch-1"),
        threading.Thread(target=total, args=([3, 4],), name="batch-2"),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    print("amount", amount)


if __name__ == "__main__":
    main()
