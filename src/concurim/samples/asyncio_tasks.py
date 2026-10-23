"""asyncio task switching: three tasks share one thread.

No Concurim imports. Only one task runs at a time; each ``await`` hands
control back to the event loop, which resumes another task.
"""

import asyncio


async def ticker(name: str, delay: float, count: int) -> None:
    """Wake up ``count`` times, ``delay`` seconds apart."""
    for _ in range(count):
        await asyncio.sleep(delay)


async def main() -> None:
    await asyncio.gather(
        asyncio.create_task(ticker("fast", 0.02, 5), name="fast"),
        asyncio.create_task(ticker("slow", 0.05, 2), name="slow"),
        asyncio.create_task(ticker("medium", 0.03, 3), name="medium"),
    )


if __name__ == "__main__":
    asyncio.run(main())
