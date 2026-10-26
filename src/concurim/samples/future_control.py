"""Futures: cancel a queued task, add a callback, collect by completion.

No Concurim imports. Two workers run four tasks. The last task is still
queued, so ``cancel()`` succeeds and it never runs. A done-callback runs on
the worker that finishes the slow task, not on the main thread.
``as_completed`` hands the futures back in the order they finish.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed


def job(name: str, seconds: float) -> str:
    """Pretend to work, then return the name."""
    time.sleep(seconds)
    return name


def announce(future) -> None:
    """Done-callback: runs on the thread that completes the future."""
    print("callback:", future.result())


def main() -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(job, "slow", 0.12),
            pool.submit(job, "quick", 0.03),
            pool.submit(job, "queued-a", 0.03),
            pool.submit(job, "queued-b", 0.03),
        ]
        futures[3].cancel()  # not started yet, so this succeeds
        futures[0].add_done_callback(announce)
        for future in as_completed(futures):
            print(
                "collected:",
                "cancelled" if future.cancelled() else future.result(),
            )


if __name__ == "__main__":
    main()
