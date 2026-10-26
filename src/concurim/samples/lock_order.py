"""Lock ordering: two threads that wait for each other.

No Concurim imports. One thread takes lock A and then wants lock B; the
other takes B and then wants A. Each holds what the other needs, so both
wait. A real deadlock would hang forever; here each wait gives up after a
timeout so the program (and the recording) can end.
"""

import threading
import time

lock_a = threading.Lock()
lock_b = threading.Lock()
TIMEOUT = 0.3


def take_both(first: threading.Lock, second: threading.Lock) -> None:
    """Hold ``first``, then try to also take ``second``."""
    with first:
        time.sleep(0.05)  # long enough for the other thread to take its lock
        if second.acquire(timeout=TIMEOUT):
            second.release()
        else:
            print("gave up waiting; releasing", first)


def main() -> None:
    threads = [
        threading.Thread(
            target=take_both, args=(lock_a, lock_b), name="A-then-B"
        ),
        threading.Thread(
            target=take_both, args=(lock_b, lock_a), name="B-then-A"
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
