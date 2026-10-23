"""A ThreadPoolExecutor running six tasks on two worker threads.

No Concurim imports. Tasks wait in the pool's queue until one of the two
workers is free; one task fails, and its exception travels to its Future.
"""

import time
from concurrent.futures import ThreadPoolExecutor

WORKERS = 2


def task(n: int) -> int:
    """A slow job; job 4 fails."""
    time.sleep(0.05)
    if n == 4:
        raise ValueError(f"job {n} failed")
    return n * n


def main() -> None:
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(task, n) for n in range(1, 7)]
    for future in futures:
        error = future.exception()
        print(error if error else future.result())


if __name__ == "__main__":
    main()
