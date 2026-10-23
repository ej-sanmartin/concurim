# Instrumentation coverage and known limitations

## Observability levels

- `none`: nothing is patched. `threads`: `threading.Thread` start and run are
  recorded. `queues`: additionally `queue.Queue` is replaced by a recording
  subclass while recording. All patches are reversed on exit.
- At `queues`, items are wrapped in envelopes, so the viewer shows queue
  operations but **not** item identity; `Queue.queue` shows envelopes to your
  code. Use `TracedQueue` for identity and lineage.
- Locks, semaphores, executors and asyncio are not instrumented yet; the home
  screen lists their examples as planned.
- A program that uses nothing the chosen level can see records zero events.
- One run at a time; a run cannot read stdin. Output is capped at 256 KiB.

## Observed (managed primitives)

- Every operation on `concurim.TracedQueue`: put, get (blocking, non-blocking,
  timeout), task_done, join, shutdown (graceful and immediate, Python 3.13+).
- Lifecycle of `concurim.TracedThread`.
- Spans marked with `concurim.work(...)`, and lineage given via
  `put(..., derived_from=...)`.

## Not observed (never implied by the viewer)

- `threading.Lock` and every other uninstrumented object. Plain `queue.Queue`
  is seen only at the `queues` level (without item identity).
- CPU scheduling and **GIL ownership**. Python-level events do not give exact
  GIL timelines. The trace records interpreter facts only (version,
  free-threaded *build*, GIL *runtime* state) so a trace can be interpreted.
- What a worker does between instrumented calls. Thread status "running (not
  blocked)" is therefore **inferred** and drawn with a dashed border.
- Which item `task_done()` refers to, unless `object_id=` is passed.
- `asyncio`, `multiprocessing`/`ProcessPoolExecutor`, `ThreadPoolExecutor`,
  locks, semaphores, events, conditions (later milestones).
- `LifoQueue`/`PriorityQueue` (items are wrapped in an envelope, which would
  break priority comparison); `SimpleQueue` (no hooks).

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
- Only macOS has been tested; the frontend bundle is ~530 kB.
- Not yet: collapsing worker groups or repetitive events, video export.

## Roadmap (not implemented)

0.2 locks/semaphores/events/conditions + ThreadPoolExecutor · 0.3 asyncio
· 0.4 process pools and a GIL/free-threaded comparison · 0.5 layout modes,
lineage browser, video export (Manim stays optional).
