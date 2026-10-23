# Concurim

**See how Python runs together.**

Concurim records what your threads actually do with instrumented queues, then
replays it as an interactive animation: which worker is running, which is
blocked and why, where every item is, and what each event means.

![Concurim viewer, dark theme](docs/images/viewer-dark.png)

*A real recording of [`examples/threaded_pipeline.py`](examples/threaded_pipeline.py)
(event 41 of 120): two producers and two consumers share a queue of capacity 3.
Items 5 and 4 are queued (the front is on the right), consumers are working on
3 and 2, and both producers are still inside a blocked `put` with items 6 and 7
in hand.*

> **Status: 0.1 (alpha).** Milestone 1: threaded producer-consumer pipelines
> with `queue.Queue`. Locks, semaphores, conditions, asyncio and process pools
> are planned. See [what is and is not observed](docs/limitations.md).

## Try it

```bash
git clone <this repo> && cd concurim
uv sync
uv run concurim demo        # records a real threaded pipeline, opens the viewer
```

Once published (not yet): `pip install concurim`, `uv tool install concurim`,
or `uvx concurim demo`.

## Record your own program

Use the traced primitives where you want to see behavior:

```python
import queue
from concurim import TracedQueue, TracedThread, work

jobs = TracedQueue(maxsize=3, name="Jobs")


def worker():
    while True:
        try:
            item = jobs.get_with_id()  # value + logical object id
        except queue.ShutDown:
            return
        with work("process", object_id=item.object_id):  # observed work span
            handle(item.value)
        jobs.task_done()


threads = [TracedThread(target=worker, name=f"worker-{i}") for i in range(2)]
...
```

Outside a recording they behave exactly like `queue.Queue` / `threading.Thread`.

```bash
uv run concurim record examples/threaded_pipeline.py          # -> threaded_pipeline.concurim
uv run concurim record -o run.concurim --include-source my_app.py arg1 arg2
uv run concurim view run.concurim
uv run concurim inspect run.concurim                           # metadata + coverage
```

Options go **before** the script; everything after the script path is passed to
your program unchanged. Or record from code:

```python
from concurim import record, TracedQueue

with record("trace.concurim"):
    jobs = TracedQueue(maxsize=5, name="Jobs")
    ...
```

When Concurim is installed as a standalone tool (`uv tool install`, `uvx`) it
runs in its own environment and cannot import *your* project's dependencies.
To record a project, install Concurim into the project
(`uv add --dev concurim`, then `uv run concurim record ...`).

## Using the viewer

| Action | How |
| --- | --- |
| Play / pause | `Space` or ▶ |
| Step forward / back | `→` / `←` (`Shift` = 10 events) |
| Beginning / end | `Home` / `End` |
| Speed | `[` `]` or the speed menu |
| Seek | scrub bar, event number box, or click/drag the timeline |
| Inspect | click a thread, the queue, or an item token |
| Source | **Source** tab (needs `--include-source`) highlights the event's line |

The explanation card describes the current event and labels anything inferred.
Dashed thread borders mean the state is *inferred* (for example "running, not
blocked"), solid borders mean it was observed.

## What you can trust

- Queue contents change only on recorded events, in true mutation order.
- *Queued* and *unfinished* are different numbers: a dequeued item leaves the
  queue but stays unfinished until `task_done()`.
- `task_done()` doesn't say which item finished; Concurim only attributes it
  when you pass `object_id=`, otherwise it labels the pairing as inferred.
- Truncated recordings, uninstrumented objects and unobservable behavior
  (CPU scheduling, the GIL) are stated in the trace and the UI.

## Privacy and security

Local only: the viewer binds `127.0.0.1`, has no telemetry or uploads, validates
traces on load (no pickle, no code execution), and serves source only from the
trace. Source and payload previews are **off by default**. A trace can contain
paths, thread names and, if enabled, code or data previews: review before
sharing. Recording changes timing. See [SECURITY.md](SECURITY.md).

## Cost

Measured on an Apple-silicon laptop, CPython 3.13 (`scripts/benchmark.py`):

| | |
| --- | --- |
| `TracedQueue` while not recording | ~2× a bare `queue.Queue` call (≈0.5 µs more) |
| Recording, detailed or light | ≈10 µs per put+get pair (≈20× a bare, work-free loop) |
| Memory while recording | ≈550 B/event (in-memory buffer) |
| Trace size | ≈19 B/event on disk (zip) |
| Load + replay | ≈1.5 s for 80k events |

Instrumentation overhead dominates only when threads do no real work; with real
work between queue operations it is usually negligible, but always re-measure.

## Development

```bash
uv sync
uv run pytest                      # unit, integration, concurrency tests
uv run ruff check . && uv run ruff format --check .
uv run ty check src
cd frontend && npm ci && npm test  # frontend logic tests
npx playwright install chromium && npm run e2e
scripts/build.sh                   # builds the viewer into the package, then uv build
scripts/smoke_wheel.sh             # installs the wheel into a clean venv and runs it
```

More: [architecture decision record](docs/adr/0001-architecture-and-reference-projects.md),
[trace format](docs/trace-format.md), [limitations](docs/limitations.md),
[contributing](CONTRIBUTING.md), [changelog](CHANGELOG.md).

MIT licensed.
