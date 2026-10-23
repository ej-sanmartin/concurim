"""A semaphore that lets only two of five threads work at once.

No Concurim imports. The semaphore holds two permits: a thread takes one to
start and gives it back when done, so the others wait for a free permit.
"""

import threading
import time

PERMITS = 2
THREADS = 5

slots = threading.Semaphore(PERMITS)


def worker() -> None:
    """Do a slow task while holding one permit."""
    with slots:
        time.sleep(0.06)


def main() -> None:
    threads = [
        threading.Thread(target=worker, name=f"worker-{i}")
        for i in range(1, THREADS + 1)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
