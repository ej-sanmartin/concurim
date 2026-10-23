"""Backpressure: a fast producer, a slow consumer, a tiny bounded queue.

The queue holds only two items, so the producer must wait for the consumer
to make room. Watch the producer block on ``put`` while the consumer works.
"""

import queue
import time

from concurim import TracedQueue, TracedThread, work

CAPACITY = 2
ITEMS = 8


def producer(jobs: TracedQueue) -> None:
    """Offer items much faster than they can be handled."""
    for n in range(ITEMS):
        time.sleep(0.01)
        jobs.put(f"item-{n}")


def consumer(jobs: TracedQueue) -> None:
    """Handle one item at a time, slowly."""
    while True:
        try:
            item = jobs.get_with_id()
        except queue.ShutDown:
            return
        with work("slow work", object_id=item.object_id):
            time.sleep(0.1)
        jobs.task_done(object_id=item.object_id)


def main() -> None:
    jobs = TracedQueue(maxsize=CAPACITY, name="Jobs")
    worker = TracedThread(target=consumer, args=(jobs,), name="consumer")
    feeder = TracedThread(target=producer, args=(jobs,), name="producer")
    worker.start()
    feeder.start()
    feeder.join()
    jobs.join()
    jobs.shutdown()
    worker.join()


if __name__ == "__main__":
    main()
