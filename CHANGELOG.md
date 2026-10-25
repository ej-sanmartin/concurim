# Changelog

## 0.1.0 (unreleased)

First vertical slice, then the GUI-first milestone, then locks, pools and
asyncio.

- Observability levels `sync` (`threading.Lock/RLock/Semaphore/
  BoundedSemaphore`, `ThreadPoolExecutor`) and `asyncio` (tasks, `Queue`,
  `Lock`, `Semaphore`); managed `TracedLock`, `TracedRLock`,
  `TracedSemaphore`, `TracedBoundedSemaphore`, `TracedThreadPoolExecutor`,
  `TracedAsync*`. Replay explains who holds or waits for each lock; asyncio
  tasks are drawn like threads; executors like queues of tasks.
- `ProcessPoolExecutor` (auto at `sync`, managed `TracedProcessPoolExecutor`):
  workers appear as processes; example `process-pool`.
- Code view: a task that has just started shades its **whole function body**,
  and a background sampler (`sample_interval_ms`, with source included) then
  follows the line each thread, asyncio task and pool worker is on (shown `≈`,
  approximate).
- Viewer: **fullscreen** animation with media-style controls (`z`), a **Code**
  mode lighting each busy worker's line in its item's colour, and a layout
  polish (orbs inside nodes, no overflowing text).
- Five more examples (lock contention, semaphore, thread pool, asyncio tasks,
  asyncio queue); queue items now keep their identity at `queues`.
- **Group workers** and `×N` folding of repeating log events.
- Viewer split into two chunks (home ~316 kB, viewer ~223 kB).
- CI: free-threaded 3.14t, and an experimental Windows job.

- Home screen: drop a `.concurim` trace, `.py` file or project folder; bundled
  examples; explicit, reviewable "Record execution" with cancel and exit codes.
- Zero-code recording levels (`--auto none|threads|queues`), reversible.
- React Flow canvas with draggable, remembered layout; Motion-animated item
  tokens; Animation/Timeline views over one recording; pacing modes; jumps.
- Local server: per-launch token on all POSTs, Origin/Host checks, body
  limits, private scratch workspaces.
- Examples moved to `src/concurim/samples` (recordings ship in the wheel).

- `TracedQueue` (`queue.Queue` subclass), `TracedThread`, `work()` spans,
  explicit lineage, `record()` API.
- `.concurim` trace format with JSON Schema, bounded buffer, truncation flag,
  optional embedded source and payload previews.
- Replay engine with per-event state, blocking/join/shutdown handling, and
  rule-based explanations that separate observed from inferred.
- Local viewer: animated producer/queue/consumer canvas, timeline with
  spans and occupancy, playback controls, source panel, inspector, event log.
- CLI: `record`, `view`, `demo`, `inspect`.
