"""asyncio.Queue: one producer task, two consumer tasks.

No Concurim imports. The queue holds two items, so the producer's ``put``
suspends when it is full and a consumer's ``get`` suspends when it is empty.
Only that one task waits; the event loop keeps running the others.
"""

import asyncio

ITEMS = 8


async def producer(jobs: asyncio.Queue) -> None:
    """Offer items faster than they are handled."""
    for n in range(ITEMS):
        await jobs.put(f"job-{n}")
        await asyncio.sleep(0.01)


async def consumer(jobs: asyncio.Queue) -> None:
    """Handle jobs until cancelled."""
    while True:
        await jobs.get()
        await asyncio.sleep(0.05)  # pretend to work
        jobs.task_done()


async def main() -> None:
    jobs: asyncio.Queue = asyncio.Queue(maxsize=2)
    workers = [
        asyncio.create_task(consumer(jobs), name=f"consumer-{i}")
        for i in (1, 2)
    ]
    await asyncio.create_task(producer(jobs), name="producer")
    await jobs.join()
    for worker in workers:
        worker.cancel()
    await asyncio.gather(*workers, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
