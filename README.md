<p align="center">
  <img src="https://raw.githubusercontent.com/ej-sanmartin/concurim/main/docs/images/logo.png" alt="Concurim" width="200"/>
  <br>
  <a href="https://github.com/ej-sanmartin/concurim/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ej-sanmartin/concurim/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <a href="https://github.com/ej-sanmartin/concurim/blob/main/CHANGELOG.md"><img alt="Version 1.0.0" src="https://img.shields.io/badge/version-1.0.0-blue"></a>
  <a href="https://github.com/ej-sanmartin/concurim/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <img alt="Python 3.13+" src="https://img.shields.io/badge/python-3.13%2B-blue">
</p>

# Concurim

**See how Python runs together.** Concurim records what your threads and
asyncio tasks actually do, then replays that one run as an animation.

![Concurim viewer, dark theme][viewer-dark]

*A recording of [`threaded_pipeline.py`][sample-pipeline]
(event 41 of 120): two producers and two consumers share a queue of
capacity 3.*

> **Status: 1.0.** Threads, queues, locks, events, barriers, pools,
> and asyncio are included.
> [What is and is not observed][doc-limits].

## Setup

From a checkout, install the project, then open the page or record a run.
`uvx concurim` is the same home screen without cloning.

```bash
git clone https://github.com/ej-sanmartin/concurim.git
cd concurim
uv sync
```

`git clone` copies the repo, `cd` enters it, and `uv sync` installs this
project and its dependencies so the commands below run with `uv run`.

```bash
uv run concurim
```

Opens the page in your browser. Drop a `.py` file or a folder, read the
plan, then click **Record execution**. Drop a `.concurim` file, or open
an example, and nothing runs.

```bash
uv run concurim demo
```

Records the bundled pipeline (the picture above) and opens it.

```bash
uv run concurim record --open --auto sync my_app.py
```

Runs `my_app.py` and writes a trace. `--auto sync` records threads,
queues, locks, events, barriers, and pools. The default is thread start
and finish. `--open` opens the viewer when the run returns. Options on
`record` come before the script; everything after the script path is
passed to your program.

```bash
uv run concurim record --open --include-source -o run.concurim my_app.py arg1
```

Runs `my_app.py` with the argument `arg1`. `--include-source` embeds
source so the Code view can show it. `-o` writes the trace to
`run.concurim` (the default path is `<script>.concurim`). This example
records threads only.

```bash
uv run concurim view run.concurim
uv run concurim inspect run.concurim
uv run concurim compare one.concurim two.concurim
```

`view` opens a saved trace. `inspect` prints when the trace was
recorded, how long it ran, and how many events it holds. `compare`
opens two recordings side by side.

```bash
uv run concurim export run.concurim -o clip.mp4 --events 5:40
```

Renders events 5 through 40 as `clip.mp4`. It only reads the trace. It
needs a Chrome-family browser and ffmpeg (`uv run --with imageio-ffmpeg`,
or `concurim[video]` once the package is published).

`uvx concurim record` cannot import a project's packages. Install it
there with `uv add --dev concurim` and use `uv run`.

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
