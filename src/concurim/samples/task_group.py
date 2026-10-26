"""asyncio.TaskGroup: structured concurrency and fail-fast.

No Concurim imports. Three tasks run inside one ``async with`` block, and
the block cannot finish until every task has. One task fails, so the group
cancels the others and raises the errors together as an ``ExceptionGroup``.
"""

import asyncio


async def fetch(name: str, seconds: float, fail: bool = False) -> str:
    """Pretend to fetch something; optionally fail afterwards."""
    await asyncio.sleep(seconds)
    if fail:
        raise ConnectionError(f"{name} refused the connection")
    return name


async def main() -> None:
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(fetch("users", 0.05), name="users")
            group.create_task(fetch("orders", 0.2), name="orders")
            group.create_task(fetch("billing", 0.1, fail=True), name="billing")
    except* ConnectionError as errors:
        print("failed:", [str(e) for e in errors.exceptions])


if __name__ == "__main__":
    asyncio.run(main())
