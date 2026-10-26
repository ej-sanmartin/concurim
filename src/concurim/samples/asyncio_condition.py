"""asyncio.Condition: tasks wait for a shared counter to reach a target.

No Concurim imports. Two waiter tasks suspend on the condition; the ticker
task increments the counter and notifies everyone. A woken task has to
re-acquire the condition's lock, and checks the predicate again.
"""

import asyncio

TARGET = 3


async def waiter(cond: asyncio.Condition, state: dict) -> None:
    """Suspend until the counter reaches the target."""
    async with cond:
        await cond.wait_for(lambda: state["count"] >= TARGET)


async def ticker(cond: asyncio.Condition, state: dict) -> None:
    """Count up, waking the waiters after every tick."""
    for _ in range(TARGET):
        await asyncio.sleep(0.03)
        async with cond:
            state["count"] += 1
            cond.notify_all()


async def main() -> None:
    cond = asyncio.Condition()
    state = {"count": 0}
    tasks = [
        asyncio.create_task(waiter(cond, state), name=f"waiter-{i}")
        for i in (1, 2)
    ]
    await asyncio.create_task(ticker(cond, state), name="ticker")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
