"""A shared counter with no lock: two processes add to it.

No Concurim imports. ``Value("i", 0, lock=False)`` is shared memory with no
lock around it, so ``counter.value += 1`` (a read, then a write) can lose an
update when two processes interleave. Concurim shows each access and the
locks held, and says that no lock is common to both writers.
"""

import multiprocessing

ROUNDS = 3


def work(counter) -> None:
    """Add one to the shared counter, several times, holding nothing."""
    for _ in range(ROUNDS):
        counter.value += 1


def main() -> None:
    counter = multiprocessing.Value("i", 0, lock=False)
    children = [
        multiprocessing.Process(target=work, args=(counter,), name=n)
        for n in ("child-1", "child-2")
    ]
    for child in children:
        child.start()
    for child in children:
        child.join()
    print("counter:", counter.value, "(expected", 2 * ROUNDS, ")")


if __name__ == "__main__":
    main()
