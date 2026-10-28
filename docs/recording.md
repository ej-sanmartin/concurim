# Recording

Two entry points do the same work. The home screen is the one to start
with. The CLI is the one to repeat.

## Home screen

`uv run concurim` (later, `uvx concurim`). Drop a `.py` file or a
project folder, or use **Run a file by path**. Choose:

- the entry-point file
- the interpreter (Concurim copies itself onto that interpreter)
- arguments
- an observability level

Read the plan. **Record execution** is what starts the program. It runs
with your user's permissions. There is no sandbox.

**Watch so far** opens the latest snapshot while the run continues. The
opened picture does not keep moving. Cancel still saves the trace, on
SIGINT or SIGTERM. On Windows, Cancel stops the process immediately, so
the file is the last snapshot, and a cancel in the first second can
save nothing.

## Command line

```bash
uv run concurim record --open --auto sync --include-source -o run.concurim app.py
```

| Flag | Effect |
| --- | --- |
| `--auto none` | Only objects your code builds with `Traced*` |
| `--auto threads` | Default. `threading.Thread` start and finish |
| `--auto queues` | Threads, plus `queue.Queue` created during the run |
| `--auto sync` | Also locks, semaphores, events, conditions, barriers, pools |
| `--auto asyncio` | Also asyncio tasks and their queues, locks, events, barriers |
| `--include-source` | Embed source so the Code view can show it |
| `--preview` | Bounded previews of small payloads. Off by default |
| `--light` | No source locations |
| `--open` | Open the viewer when the run returns |
| `-o path` | Trace path. Default is `<script>.concurim` |

Only objects your own code creates during the recording are patched.
A lock created inside the standard library, or before recording starts,
stays invisible. `uvx concurim record` cannot import your project's
packages. Install Concurim into that project (`uv add --dev concurim`)
and use `uv run concurim record`.

## From Python

```python
from concurim import record

with record("trace.concurim", auto="sync", include_source=True):
    main()
```

`TracedQueue`, `TracedLock`, `TracedThread`, and the other `Traced*`
classes are worth it when you want item identity, a work span, or
lineage (`derived_from`). Outside a recording they behave like the
standard objects. For a plain program, `--auto` is enough.
