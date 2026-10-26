"""multiprocessing.Process: a copied list versus a shared counter.

No Concurim imports. All children get the same two arguments. The list is
copied into each child, so what a child appends is lost. The counter is a
shared value, so every child's increments are visible to the parent.
"""

import multiprocessing


def work(counter, notes: list[str]) -> None:
    """Add one to the shared counter and one note to the copied list."""
    with counter.get_lock():
        counter.value += 1
    notes.append("done")


def main() -> None:
    counter = multiprocessing.Value("i", 0)  # shared memory
    notes: list[str] = []  # an ordinary list: each child gets a copy
    children = [
        multiprocessing.Process(target=work, args=(counter, notes), name=n)
        for n in ("child-1", "child-2", "child-3")
    ]
    for child in children:
        child.start()
    for child in children:
        child.join()
    print("counter:", counter.value, "notes:", notes)


if __name__ == "__main__":
    main()
