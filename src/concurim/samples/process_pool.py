"""A ProcessPoolExecutor spreading CPU-bound work over three processes.

No Concurim imports. Each task runs in a separate worker *process*, so the
tasks really run in parallel, not just concurrently. The viewer shows when
each task starts and ends in each worker (nothing inside a worker).
"""

from concurrent.futures import ProcessPoolExecutor

WORKERS = 3


def count_primes(limit: int) -> int:
    """CPU-bound work: how many primes are below ``limit``."""
    found = 0
    for n in range(2, limit):
        if all(n % d for d in range(2, int(n**0.5) + 1)):
            found += 1
    return found


def main() -> None:
    limits = [60_000, 30_000, 80_000, 20_000, 70_000, 40_000, 50_000, 10_000]
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        results = pool.map(count_primes, limits)
        for limit, primes in zip(limits, results, strict=True):
            print(f"{primes} primes below {limit}")


if __name__ == "__main__":
    main()
