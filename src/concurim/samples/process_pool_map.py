"""multiprocessing.Pool: map() over items, one task per item.

No Concurim imports. ``Pool.map`` hands each item to a worker process.
Items travel to the worker as copies and results travel back as copies;
nothing is shared unless you set that up yourself.
"""

import multiprocessing

WORKERS = 2


def slow_square(n: int) -> int:
    """CPU-bound work: square ``n`` after counting a lot."""
    total = 0
    for i in range(400_000):
        total += i % (n + 1)
    return n * n


def main() -> None:
    with multiprocessing.Pool(WORKERS) as pool:
        print(pool.map(slow_square, range(6)))


if __name__ == "__main__":
    main()
