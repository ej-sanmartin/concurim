"""CPU-bound work on a thread pool: the program to compare across builds.

No Concurim imports. Four threads each count primes, which keeps the CPU
busy the whole time. On a standard build only one thread runs Python code
at a time (the GIL); on a free-threaded build they can run side by side.
Record it under each interpreter and open both in Compare to see what
differs. The viewer only shows when each task started and ended, not who
held the GIL.
"""

from concurrent.futures import ThreadPoolExecutor

WORKERS = 4
LIMIT = 60_000


def count_primes(limit: int) -> int:
    """CPU-bound work: how many primes are below ``limit``."""
    found = 0
    for n in range(2, limit):
        if all(n % d for d in range(2, int(n**0.5) + 1)):
            found += 1
    return found


def main() -> None:
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(count_primes, [LIMIT] * WORKERS))
    print(results)


if __name__ == "__main__":
    main()
