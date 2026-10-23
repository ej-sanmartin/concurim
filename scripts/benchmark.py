"""Measure Concurim's recording overhead.

Compares ``queue.Queue`` with ``TracedQueue`` (not recording, light mode,
detailed mode) on a single-thread put/get loop and a threaded pipeline, and
reports event throughput, memory and trace size.

Usage: uv run python scripts/benchmark.py [--ops 50000] [--items 20000]
"""

import argparse
import queue
import tempfile
import threading
import time
import tracemalloc
from pathlib import Path

import concurim
from concurim import RecorderConfig, TracedQueue, record


def loop(q, ops):
    start = time.perf_counter()
    for i in range(ops):
        q.put(i)
        q.get()
    return time.perf_counter() - start


def pipeline(make_queue, items, workers=4):
    q = make_queue()
    done = object()

    def producer():
        for i in range(items // workers):
            q.put(i)

    def consumer():
        while q.get() is not done:
            pass

    cons = [threading.Thread(target=consumer) for _ in range(workers)]
    prods = [threading.Thread(target=producer) for _ in range(workers)]
    start = time.perf_counter()
    for t in cons + prods:
        t.start()
    for t in prods:
        t.join()
    for _ in cons:
        q.put(done)
    for t in cons:
        t.join()
    return time.perf_counter() - start


def best(fn, repeat=5):
    return min(fn() for _ in range(repeat))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ops", type=int, default=50_000)
    ap.add_argument("--items", type=int, default=20_000)
    args = ap.parse_args()
    ops, items = args.ops, args.items

    rows = []
    base = best(lambda: loop(queue.Queue(), ops))
    rows.append(("queue.Queue", base, None))
    t = best(lambda: loop(TracedQueue(), ops))
    rows.append(("TracedQueue (not recording)", t, None))
    for label, cfg in (
        ("TracedQueue light", RecorderConfig.light()),
        ("TracedQueue detailed", RecorderConfig()),
    ):

        def run(cfg=cfg):
            with record(config=cfg):
                return loop(TracedQueue(), ops)

        rows.append((label, best(run), None))
    print(f"\nsingle-thread put+get x {ops:,} (best of 5)")
    for name, secs, _ in rows:
        us = secs / ops * 1e6
        print(
            f"  {name:32s} {secs:7.3f}s  {us:6.2f} us/pair  x{secs / base:5.2f}"
        )

    pbase = best(lambda: pipeline(queue.Queue, items), 3)
    print(f"\n4 producers / 4 consumers, {items:,} items (best of 3)")
    print(f"  {'queue.Queue':32s} {pbase:7.3f}s")
    for label, cfg in (
        ("TracedQueue light", RecorderConfig.light()),
        ("TracedQueue detailed", RecorderConfig()),
    ):

        def run(cfg=cfg):
            with record(config=cfg):
                return pipeline(TracedQueue, items)

        s = best(run, 3)
        print(f"  {label:32s} {s:7.3f}s  x{s / pbase:5.2f}")

    # events, memory and size for one detailed recording
    tmp = Path(tempfile.mkdtemp()) / "bench.concurim"
    tracemalloc.start()
    t0 = time.perf_counter()
    with record(tmp) as rec:
        pipeline(TracedQueue, items)
    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    n = len(rec.events())
    print(f"\ndetailed recording of the {items:,}-item pipeline")
    print(
        f"  events:            {n:,}  ({n / elapsed:,.0f} events/s incl. app)"
    )
    print(
        f"  peak traced mem:   {peak / 1e6:.1f} MB "
        f"({peak / max(n, 1):.0f} B/event, buffer + app)"
    )
    size = tmp.stat().st_size
    print(f"  trace on disk:     {size / 1e6:.2f} MB ({size / n:.1f} B/event)")
    t1 = time.perf_counter()
    replay = concurim.build_replay(concurim.load_trace(tmp))
    print(
        f"  load + replay:     {time.perf_counter() - t1:.2f}s "
        f"({len(replay['frames']):,} frames)"
    )


if __name__ == "__main__":
    main()
