<p align="center">
  <img src="https://raw.githubusercontent.com/ej-sanmartin/concurim/main/docs/images/logo.png" alt="Concurim" width="200"/>
</p>

# Concurim

**See how Python runs together.** Concurim records what your threads and
asyncio tasks actually do, then replays that one run as an animation.

## Setup

`uvx concurim` opens the home screen. From a checkout:

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

![Concurim viewer, dark theme][viewer-dark]

*A recording of [`threaded_pipeline.py`][sample-pipeline]
(event 41 of 120): two producers and two consumers share a queue of
capacity 3.*

> **Status: 1.0.** Threads, queues, locks, events, barriers, pools,
> and asyncio are included.
> [What is and is not observed][doc-limits].

## Guide

| | |
| --- | --- |
| [Getting started][doc-start] | The page, the commands, a stuck run |
| [Concepts][doc-concepts] | One schedule, observed versus inferred, what you can trust |
| [Recording][doc-recording] | Home screen, `--auto`, `record()`, `Traced*` |
| [Reading a run][doc-reading] | Animation, Code, Timeline, compare, export |
| [Teaching][doc-teaching] | Which example to open |
| [Cost][doc-cost] | Overhead of recording |
| [Limitations][doc-limits] | Caveats |
| [Trace format][doc-trace] | The `.concurim` file |
| [Security][doc-security] | Local only. Review a trace before sharing it |
| [Contributing][doc-contributing] | Tests, style, publishing |
| [Changelog][doc-changelog] | What 1.0.0 contains |

The viewer binds `127.0.0.1` and has no telemetry. Source and payload
previews are off unless you ask for them.

MIT licensed.

[viewer-dark]: https://raw.githubusercontent.com/ej-sanmartin/concurim/main/docs/images/viewer-dark.png
[sample-pipeline]: https://github.com/ej-sanmartin/concurim/blob/main/src/concurim/samples/threaded_pipeline.py
[doc-start]: https://github.com/ej-sanmartin/concurim/blob/main/docs/getting-started.md
[doc-concepts]: https://github.com/ej-sanmartin/concurim/blob/main/docs/concepts.md
[doc-recording]: https://github.com/ej-sanmartin/concurim/blob/main/docs/recording.md
[doc-reading]: https://github.com/ej-sanmartin/concurim/blob/main/docs/reading-a-run.md
[doc-teaching]: https://github.com/ej-sanmartin/concurim/blob/main/docs/teaching.md
[doc-cost]: https://github.com/ej-sanmartin/concurim/blob/main/docs/cost.md
[doc-limits]: https://github.com/ej-sanmartin/concurim/blob/main/docs/limitations.md
[doc-trace]: https://github.com/ej-sanmartin/concurim/blob/main/docs/trace-format.md
[doc-security]: https://github.com/ej-sanmartin/concurim/blob/main/SECURITY.md
[doc-contributing]: https://github.com/ej-sanmartin/concurim/blob/main/CONTRIBUTING.md
[doc-changelog]: https://github.com/ej-sanmartin/concurim/blob/main/CHANGELOG.md
