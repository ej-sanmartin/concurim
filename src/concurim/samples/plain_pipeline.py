"""An ordinary threaded pipeline: no Concurim imports at all.

Only the standard library is used. Concurim can still record it:

* ``--auto threads`` sees the threads (who started, when they finished) but
  nothing about the queue.
* ``--auto queues`` also sees every ``put`` and ``get`` on the queue.

Compare the two recordings of this same file in the gallery.
"""

import queue
import threading
import time

PRODUCERS = 2
CONSUMERS = 2
ITEMS_PER_PRODUCER = 5
STOP = None  # sentinel telling a consumer to exit


def producer(jobs: queue.Queue, name: int) -> None:
    """Put a few jobs on the queue."""
    for n in range(ITEMS_PER_PRODUCER):
        time.sleep(0.02)
        jobs.put(f"P{name}-job-{n}")


def consumer(jobs: queue.Queue) -> None:
    """Handle jobs until a stop sentinel arrives."""
    while True:
        item = jobs.get()
        if item is STOP:
            jobs.task_done()
            return
        time.sleep(0.08)  # pretend to work
        jobs.task_done()


def main() -> None:
    jobs: queue.Queue = queue.Queue(maxsize=3)
    consumers = [
        threading.Thread(target=consumer, args=(jobs,), name=f"consumer-{i}")
        for i in range(1, CONSUMERS + 1)
    ]
    producers = [
        threading.Thread(target=producer, args=(jobs, i), name=f"producer-{i}")
        for i in range(1, PRODUCERS + 1)
    ]
    for thread in consumers + producers:
        thread.start()
    for thread in producers:
        thread.join()
    for _ in consumers:
        jobs.put(STOP)
    for thread in consumers:
        thread.join()


if __name__ == "__main__":
    main()
