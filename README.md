<p align="center">
  <img src="docs/images/logo.png" alt="Concurim" width="200"/>
</p>

# Concurim

**See how Python runs together.** Concurim records what your threads and
asyncio tasks actually do, then replays that one run as an animation.

## Setup

From a checkout. After 0.1.0 is on PyPI, `uvx concurim` opens the same
home screen.

```bash
git clone https://github.com/ej-sanmartin/concurim.git
cd concurim
uv sync

uv run concurim
uv run concurim demo
uv run concurim record --open --auto sync my_app.py
uv run concurim record --open --include-source -o run.concurim my_app.py arg1
uv run concurim view run.concurim
uv run concurim inspect run.concurim
uv run concurim compare one.concurim two.concurim
uv run concurim export run.concurim -o clip.mp4 --events 5:40
```

`uv run concurim` opens the page. Drop a `.py` file or a folder, read the
plan, then click **Record execution**. Drop a `.concurim` file, or open
an example, and nothing runs. Options on `record` come before the script.
`uvx concurim record` cannot import a project's packages; install it
there with `uv add --dev concurim` and use `uv run`.

![Concurim viewer, dark theme](docs/images/viewer-dark.png)

*A recording of [`threaded_pipeline.py`](src/concurim/samples/threaded_pipeline.py)
(event 41 of 120): two producers and two consumers share a queue of
capacity 3.*

> **Status: 0.1 (alpha).** Not on PyPI yet. Threads, queues, locks,
> events, barriers, pools, and asyncio are included.
> [What is and is not observed](docs/limitations.md).

## Guide

| | |
| --- | --- |
| [Getting started](docs/getting-started.md) | The page, the commands, a stuck run |
| [Concepts](docs/concepts.md) | One schedule, observed versus inferred, what you can trust |
| [Recording](docs/recording.md) | Home screen, `--auto`, `record()`, `Traced*` |
| [Reading a run](docs/reading-a-run.md) | Animation, Code, Timeline, compare, export |
| [Teaching](docs/teaching.md) | Which example to open |
| [Cost](docs/cost.md) | Overhead of recording |
| [Limitations](docs/limitations.md) | Caveats |
| [Trace format](docs/trace-format.md) | The `.concurim` file |
| [Security](SECURITY.md) | Local only. Review a trace before sharing it |
| [Contributing](CONTRIBUTING.md) | Tests, style, publishing |
| [Changelog](CHANGELOG.md) | What 0.1.0 contains |

The viewer binds `127.0.0.1` and has no telemetry. Source and payload
previews are off unless you ask for them.

MIT licensed.
