# Trace format (`.concurim`, format_version 1)

A trace is a zip archive:

```text
metadata.json     one JSON object (see below)
events.jsonl      one event per line, in recording order
sources/N.txt     optional source text, only with --include-source
```

Loading is defensive: member names are looked up exactly (nothing is extracted
to disk), sizes are capped (metadata 1 MiB, events 512 MiB / 5 M events, each
source 1 MiB / 500 sources), every field is type-checked, `sequence` must
strictly increase per process, and unknown `schema_version`/`format_version`
are rejected. Nothing is unpickled or executed.

## metadata.json

| key | meaning |
| --- | --- |
| `format`, `format_version` | `"concurim-trace"`, `1` |
| `schema_version` | version of the event schema (`1`) |
| `concurim_version`, `created_at_utc`, `duration_ns` | provenance |
| `event_count`, `dropped_events`, `truncated` | **loss is explicit**: when the buffer limit is hit new events are dropped and `truncated` is true |
| `config` | recording options used (`include_source`, `preview`, ...) |
| `environment` | implementation, version, `free_threaded_build` (build capability), `gil_enabled` (runtime state or `null`), platform |
| `coverage.observed` / `coverage.not_observed` | what this recorder can and cannot see |
| `program` | script name, `exit_code`, `exception` type if any |
| `sources` | map of display path to `sources/N.txt` |

## Events

Schema: [`src/concurim/schema/event.schema.json`](../src/concurim/schema/event.schema.json).

| field | meaning |
| --- | --- |
| `event_id`, `sequence` | unique id; **total order within one process** (assigned under the collector lock) |
| `timestamp_ns` | monotonic ns since recording start (never wall clock) |
| `process_id`, `thread_id`, `task_id` | logical identities (`thread-2`, not OS ids, which get reused) |
| `resource_id`, `object_id`, `operation_id` | queue/lock id; logical item id; ties started/blocked/completed of one call |
| `caused_by` | explicit causal predecessor, e.g. a get's `caused_by` is the put that enqueued the item, a started thread's is its `start()` call |
| `source` | `file`, `line`, `function` of the user code that triggered it (relative to the start directory when inside it) |
| `metadata` | at most 24 scalar values, strings ≤ 512 chars |

Cross-process ordering is **not** assumed: only per-process `sequence` and
explicit `caused_by` edges are reliable.

### Pool metadata

`thread.registered` carries `actor_kind` (`thread`, `task`, `process`).
For `ProcessPoolExecutor`, `executor.created` has `pool: process`; worker
events carry `worker_pid`, and `child_ns` holds the worker's own monotonic
clock (informational; ordering uses the parent's receive time).

### Queue events

`queue.created`, `queue.put.{started,blocked,completed,timeout,failed}`,
`queue.get.{started,blocked,completed,timeout,failed}`, `queue.task_done`,
`queue.task_done.failed`, `queue.join.{started,completed,failed}`,
`queue.shutdown.requested`, `queue.item.discarded`.

Semantics worth knowing:

- `put.completed` / `get.completed` / `item.discarded` are emitted while the
  queue's mutex is held, so their order is the real order of queue mutations.
- `blocked` means the queue was full (put) or empty (get) when the call first
  tried; the operation may complete immediately after.
- `task_done` and `shutdown.requested` are emitted just *before* the call so
  any thread they wake records its events afterwards.
- `put_nowait`/`get_nowait` appear as `block: false` on a single started event.

### Lock and semaphore events

`lock.created`, `lock.acquire.{started,blocked,completed,failed}`,
`lock.released`, and the same family under `semaphore.` (including
`BoundedSemaphore`, and asyncio's `Lock`/`Semaphore`). `created` carries
`metadata.kind` (`lock`, `rlock` or `semaphore`), `value` and `name`;
`released` carries `count` for semaphores.

- `blocked` means the lock was unavailable at the first try.
- `released` is emitted just *before* the real release, so the next holder's
  `acquire.completed` always has a larger `sequence`.

### Executor events

`executor.created` (`max_workers`), `executor.submit` (carries `object_id` for
the submitted task and `operation_id`), `executor.task.{started,finished,failed}`
(on the worker thread), `executor.shutdown` (`wait`, `cancel_futures`). The
replay draws an executor as a queue of pending tasks.

### asyncio task events

`task.created`, `task.step.{started,ended}` (one per run of the task by the
event loop; `ended` has `done`), `task.finished`, `task.failed`,
`task.cancelled`. These events carry `task_id` and `thread_id` (the loop's
thread); the replay treats `task_id` (else `thread_id`) as the *actor*. Within
one loop at most one task has an open step at any time.

### Other events

`thread.registered` (first event seen from a thread), `thread.start.requested`,
`thread.started`, `thread.finished`, `thread.failed`, `work.started`,
`work.finished`, `work.failed`, `object.derived` (explicit lineage),
`code.sampled` (approximate current line of an actor, from the background
sampler; only with source included. It is not a state change: the replay moves
these to `line_samples` and leaves them out of `events`).

## Replay document

`concurim.build_replay(trace)` (also served at `/api/replay`) returns the
events plus one *frame* per event: changed entity states (`threads` for
threads and asyncio tasks, `queues` for queues and executors, `syncs` for
locks and semaphores; a waiting actor has `waiting_on: {resource, op}`), an explanation
`{title, text, tone, inferred[]}`, and an optional `motion`. Queue frames carry
`size` (true occupancy) and at most the first 64 `items`. The same trace
always produces the same document.

For the code view it also carries `code_ranges` (per source file, the first
and last line of every function, from parsing the embedded source) and
`line_samples` (`{at, actor, file, line, function}`, where `at` is the index of
the last event before the sample).
