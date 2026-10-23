"""Lock contention: four threads share one lock.

No Concurim imports. Each thread needs the lock for a short critical
section, so only one can be inside at a time; the others wait their turn.
"""

import threading
import time

THREADS = 4
ROUNDS = 2

lock = threading.Lock()
total = 0


def worker() -> None:
    """Repeatedly update shared state under the lock."""
    global total
    for _ in range(ROUNDS):
        with lock:
            time.sleep(0.04)  # the critical section
            total += 1
        time.sleep(0.01)  # work outside the lock


def main() -> None:
    threads = [
        threading.Thread(target=worker, name=f"worker-{i}")
        for i in range(1, THREADS + 1)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    print("total", total)


if __name__ == "__main__":
    main()
