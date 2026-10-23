"""Recording dropped programs at the sync and asyncio levels."""

import textwrap

import pytest
from viewer_client import Client, serve, stop

LOCKS = textwrap.dedent(
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor
    lock = threading.Lock()
    sem = threading.Semaphore(2)
    total = 0
    def bump(_):
        global total
        with lock:
            total += 1
        with sem:
            pass
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(bump, range(4)))
    print("total", total)
    """
)

ASYNC = textwrap.dedent(
    """
    import asyncio
    async def work(q, n):
        await q.put(n)
    async def main():
        q = asyncio.Queue(maxsize=1)
        lock = asyncio.Lock()
        async def drain():
            for _ in range(3):
                async with lock:
                    await q.get()
        tasks = [asyncio.create_task(work(q, n)) for n in range(3)]
        await asyncio.gather(drain(), *tasks)
    asyncio.run(main())
    print("ok")
    """
)


@pytest.fixture
def client(tmp_path):
    server = serve(tmp_path)
    yield Client(server)
    stop(server)


def record(client, code, level):
    ws = client.upload({"main.py": code})
    body = {"workspace_id": ws["id"], "entry": ws["suggested"], "auto": level}
    status, plan = client.post_json("/api/runs/plan", body)
    assert status == 201, plan
    assert client.post_json(f"/api/runs/{plan['id']}/start")[0] == 202
    run = client.wait_run(plan["id"])
    assert run["state"] == "finished", run["output"]
    return client.get_json("/api/replay")


def test_sync_level_records_locks_semaphores_and_the_pool(client):
    replay = record(client, LOCKS, "sync")
    assert replay["warnings"] == []
    entities = replay["entities"]
    kinds = sorted(s["kind"] for s in entities["syncs"].values())
    assert kinds == ["lock", "semaphore"]
    assert [q["kind"] for q in entities["queues"].values()] == ["executor"]
    span_kinds = {s["kind"] for s in replay["spans"]}
    assert "hold" in span_kinds


def test_queues_level_does_not_claim_to_see_locks(client):
    replay = record(client, LOCKS, "queues")
    assert replay["entities"]["syncs"] == {}
    not_seen = " ".join(replay["metadata"]["coverage"]["not_observed"])
    assert "lock" in not_seen.lower()


def test_asyncio_level_records_tasks_queue_and_lock(client):
    replay = record(client, ASYNC, "asyncio")
    assert replay["warnings"] == []
    entities = replay["entities"]
    tasks = [t for t in entities["threads"].values() if t["kind"] == "task"]
    assert len(tasks) >= 4
    assert len(entities["queues"]) == 1 and len(entities["syncs"]) == 1


def test_unknown_level_is_rejected(client):
    ws = client.upload({"main.py": "print(1)\n"})
    body = {"workspace_id": ws["id"], "entry": ws["suggested"], "auto": "x"}
    assert client.post_json("/api/runs/plan", body)[0] == 400
