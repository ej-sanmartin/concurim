"""Cancellation: shut a queue down immediately while work is pending.

``shutdown(immediate=True)`` discards the items still queued and wakes the
consumers, which then exit. Items already being processed still finish.
"""

import queue
import time

from concurim import TracedQueue, TracedThread, work

ITEMS = 9


def consumer(jobs: TracedQueue) -> None:
    """Process items until the queue is shut down."""
    while True:
        try:
            item = jobs.get_with_id()
        except queue.ShutDown:
            return
        with work("process", object_id=item.object_id):
            time.sleep(0.1)
        jobs.task_done(object_id=item.object_id)


def main() -> None:
    jobs = TracedQueue(name="Jobs")
    workers = [
        TracedThread(target=consumer, args=(jobs,), name=f"worker-{i}")
        for i in (1, 2)
    ]
    for thread in workers:
        thread.start()
    for n in range(ITEMS):
        jobs.put(f"job-{n}")
    time.sleep(0.15)  # a few jobs finish, the rest are still queued
    jobs.shutdown(immediate=True)  # cancel: discard whatever is queued
    for thread in workers:
        thread.join()


if __name__ == "__main__":
    main()
