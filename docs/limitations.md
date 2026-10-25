# Instrumentation coverage and known limitations

## Observability levels

- Levels are cumulative: `none` (nothing patched) < `threads`
  (`threading.Thread` start and run) < `queues` (`queue.Queue`) < `sync`
  (`threading.Lock`, `RLock`, `Semaphore`, `BoundedSemaphore`,
  `ThreadPoolExecutor`) < `asyncio` (tasks, `asyncio.Queue`, `Lock`,
  `Semaphore`, `BoundedSemaphore`). Everything is patched only while
  recording and reversed on exit.
- Only objects **created directly by your code** are traced at `sync` and
  `asyncio`. Locks that the standard library or a package creates for itself
  (logging, `queue.Queue`'s own mutex, ...) are left alone.
- At `queues`/`asyncio`, queue items have identity: the recorder stores items
  in a transparent container, so `Queue.queue` and `qsize()` show your
  original objects. Use `TracedQueue` for lineage (`derived_from`).
- While recording at `sync`, `isinstance(x, threading.Lock)` is `False` for
  locks the program creates (`threading.Lock` is a factory function, so
  Concurim has to replace it). `type(x)` is a Concurim class there too.
- Objects created **before** recording starts (module-level locks created at
  import time, executors in an already imported library) are not traced.
- asyncio: a task is recorded when it is created and each time the event loop
  runs a step of it. What it awaits when that is not an instrumented object
  (for example `asyncio.sleep`) is shown as "suspended (awaiting)". Tasks
  started eagerly (`eager_task_factory`) lose their first step, and `uvloop`
  is not supported.
- `ThreadPoolExecutor`: submit, task start/finish/failure and shutdown are
  recorded; `Future` callbacks, `cancel()` and `as_completed` ordering are not.
- A program that uses nothing the chosen level can see records zero events.
- One run at a time; a run cannot read stdin. Output is capped at 256 KiB.

## Observed (managed primitives)

- Every operation on `concurim.TracedQueue`: put, get (blocking, non-blocking,
  timeout), task_done, join, shutdown (graceful and immediate, Python 3.13+).
- Lifecycle of `concurim.TracedThread`.
- Spans marked with `concurim.work(...)`, and lineage given via
  `put(..., derived_from=...)`.

## Not observed (never implied by the viewer)

- Anything the chosen level does not patch: plain `queue.Queue` is seen from
  `queues` on, locks/semaphores/executors from `sync`, asyncio from
  `asyncio`; the trace and the **Trace** tab say which applies.
- CPU scheduling and **GIL ownership**. Python-level events do not give exact
  GIL timelines. The trace records interpreter facts only (version,
  free-threaded *build*, GIL *runtime* state) so a trace can be interpreted.
- What a worker does between instrumented calls, beyond the sampled line of
  the code view. Thread status "running (not blocked)" is therefore
  **inferred** and drawn with a dashed border.
- Which item `task_done()` refers to, unless `object_id=` is passed.
- `multiprocessing` (`Pool`, `Process`), `threading.Event`, `Condition`,
  `Barrier`, `asyncio.Event`/`Condition` (later milestones).
- `LifoQueue`/`PriorityQueue` (items are wrapped in an envelope, which would
  break priority comparison); `SimpleQueue` (no hooks).

## ProcessPoolExecutor

- Workers are shown as processes (`SpawnProcess-N`); tasks flow through the
  pool like thread-pool tasks. Start, finish and failure of each task are
  seen. With source included, the code view also follows the worker's line.
- Timestamps are taken in the parent when a worker's report arrives, so they
  can lag the real moment slightly. The worker's own clock is kept as
  `child_ns` but never compared across processes.
- Tasks, arguments and results are pickled by Python as usual; the pool's
  internal threads and queues are hidden.
- Other process APIs (`multiprocessing.Pool`, `Process`) are not covered.

## Code view

- A pool task or thread target starts at its function: until the position
  inside it is known, the **whole function body** is shaded. Blocked calls and
  awaits sit on the exact line.
- With source included, a background thread samples where each thread, asyncio
  task and process-pool worker is every `sample_interval_ms` (default 5 ms;
  `0` turns it off) and records `code.sampled`. Sampled lines are drawn with
  a `≈` and are **approximate**: a line shorter than the interval can be
  missed, and CPython only lets the sampler look when a thread yields the GIL,
  so a tight loop usually shows its last line, and blocking calls (`sleep`,
  I/O, locks) are over-represented.
- Samples are stored in the trace but kept out of the event list, timeline and
  playback. At most 100,000 samples per process are kept; after that the
  code view is stale (the viewer warns for the main process; pool workers
  stop silently). Sampling slows the program a little.
- A sample only follows user code (files under the script's folder, never
  installed packages); the innermost such frame wins, so a helper function in
  another file is shown there.
- Needs source in the trace (`--include-source`); otherwise a hint is shown.

## Behavior you should know about

- Recording changes timing (≈10 µs per put/get pair). Concurrency bugs that
  depend on timing can appear, disappear or move.
- Start recording **before** creating queues and putting items. Items put
  before recording are consumed as "untracked" and the replay warns.
- `blocked` reflects what the caller observed at call time; a very fast
  consumer can make the following blocking call return immediately.
- Subclasses of `TracedThread` that override `run()` without calling
  `super().run()` are not recorded.
- `shutdown()`'s "requested" event precedes the flag flip by design. A getter
  that wins the race for the mutex right after may still dequeue an item.
- Buffer limit (`max_events`, default 1 M): new events are dropped, the trace is
  marked `truncated`, and the viewer shows a warning.
- Workers that never call `task_done()` show at most their 8 most recent
  received items.
- Queues with thousands of items: frames carry the first 64 item ids and the
  true `size`; the inspector shows "+N more". Replay time is roughly linear in
  events (~19 µs/event) but the replay document grows with trace size; traces
  beyond a few hundred thousand events are not yet supported smoothly.
- The timeline draws one tick per event only up to 4,000 events; larger
  traces show spans and occupancy but not individual ticks.
- Visual regression baselines are per platform (macOS baselines committed).
- Tested on macOS (CPython 3.13, 3.14 and the free-threaded 3.14t build,
  where the full suite passes with the GIL off). Linux, and Windows, run in
  CI; the Windows job is marked experimental and its process-control code
  (`viewer/procs.py`) has never been run by the maintainers. On Windows,
  **Cancel** terminates the program at once (there is no Ctrl-C to send), so
  no trace is saved for a cancelled run.
- The viewer is split in two JavaScript chunks: ~316 kB loaded on the home
  screen and ~223 kB (React Flow) loaded when a recording is opened.
- Large graphs: groups of 4 or more similar workers can be collapsed
  (**Group workers**; automatic above 24 actors). Runs of repeating events in
  the log fold into one row (`×N`).
- Not yet: video export.

## Roadmap (not implemented)

Events/conditions/barriers · `multiprocessing.Pool` and a GIL/free-threaded
comparison · layout modes, lineage browser, video export (Manim stays
optional).
