"""A bounded producer-consumer pipeline built from real threads.

Two producers feed one bounded queue; two consumers drain it. Producers are
faster than consumers, so the queue fills up (backpressure) and consumers
sometimes wait for work. Run it directly, or record it with::

    concurim record examples/threaded_pipeline.py
"""

import queue
import time

from concurim import TracedQueue, TracedThread, work

PRODUCERS = 2
CONSUMERS = 2
ITEMS_PER_PRODUCER = 6
QUEUE_SIZE = 3


def producer(jobs: TracedQueue, name: int, count: int) -> None:
    """Put ``count`` jobs on the queue, one every few milliseconds."""
    for n in range(count):
        time.sleep(0.02)
        jobs.put(f"P{name}-job-{n}")


def consumer(jobs: TracedQueue, results: list[str]) -> None:
    """Process jobs until the queue is shut down."""
    while True:
        try:
            item = jobs.get_with_id()
        except queue.ShutDown:
            return
        with work("process", object_id=item.object_id):
            time.sleep(0.12)
            results.append(item.value.upper())
        jobs.task_done()


def main() -> None:
    jobs = TracedQueue(maxsize=QUEUE_SIZE, name="Jobs")
    results: list[str] = []
    consumers = [
        TracedThread(
            target=consumer, args=(jobs, results), name=f"consumer-{i}"
        )
        for i in range(1, CONSUMERS + 1)
    ]
    producers = [
        TracedThread(
            target=producer,
            args=(jobs, i, ITEMS_PER_PRODUCER),
            name=f"producer-{i}",
        )
        for i in range(1, PRODUCERS + 1)
    ]
    for thread in consumers:
        thread.start()
    time.sleep(0.05)  # let consumers wait on the empty queue first
    for thread in producers:
        thread.start()
    for thread in producers:
        thread.join()
    jobs.join()  # wait until every job has been marked done
    jobs.shutdown()  # wake idle consumers so they can exit
    for thread in consumers:
        thread.join()
    print(f"processed {len(results)} jobs")


if __name__ == "__main__":
    main()
