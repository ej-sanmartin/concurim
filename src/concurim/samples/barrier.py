"""threading.Barrier: three workers leave together.

No Concurim imports. Each worker arrives at a barrier of three. The first
two wait. The third arrival releases all of them at once.
"""

import threading
import time

meet = threading.Barrier(3)


def worker(lane: int) -> None:
    """Arrive, then continue only with the others."""
    time.sleep(0.02 * lane)
    meet.wait()


def main() -> None:
    threads = [
        threading.Thread(target=worker, args=(lane,), name=f"worker-{lane}")
        for lane in (1, 2, 3)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
