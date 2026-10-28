# Getting started

Open the home screen and drop a program, or record from the terminal.
Either way you get one picture of the run that actually happened.

Commands below use `uv run concurim` from a checkout of this repo.
`uvx concurim` is the same home screen. `uv add --dev concurim` is how
`concurim record` can import a project's own packages.

## Open the page

```bash
git clone https://github.com/ej-sanmartin/concurim.git
cd concurim
uv sync
uv run concurim
```

The browser opens on this computer. From there:

- Drop a `.concurim` file, or open an example. Nothing runs.
- Drop a `.py` file or a project folder. Pick the entry point,
  interpreter, arguments, and observability level, read the plan, then
  click **Record execution**. The program does not run until that click.
  When it finishes, the picture opens.
- **Watch so far**, while a run is still going, opens the latest saved
  moment. That picture stays where you opened it.

```bash
uv run concurim --port 8794 --no-browser   # page only, you open the URL
```

## Record from the terminal

Options come before the script. Everything after the script path is
passed to your program.

```bash
uv run concurim record --open my_app.py
uv run concurim record --open --auto sync my_app.py
uv run concurim record --open --include-source -o run.concurim my_app.py arg1
uv run concurim view run.concurim
uv run concurim inspect run.concurim
```

`--auto` defaults to `threads`. Use `queues`, `sync`, or `asyncio` when
the program uses those primitives and does not import Concurim itself.
`--include-source` is what the Code view needs. A file that does not
compile is refused, and no trace is written.

```bash
uv run concurim demo
uv run concurim compare one.concurim two.concurim
uv run concurim export run.concurim -o clip.mp4 --events 5:40
```

`demo` records the bundled pipeline and opens it. `export` needs a
Chrome-family browser and ffmpeg (`uv run --with imageio-ffmpeg`, or
`concurim[video]` once the package is published). It only reads the
trace.

Ctrl-C during `record` still leaves a trace. Playback ends at the last
observed event. See [limitations](limitations.md) for what a stuck run
can and cannot show.

Next: [concepts](concepts.md), [recording](recording.md),
[reading a run](reading-a-run.md).
