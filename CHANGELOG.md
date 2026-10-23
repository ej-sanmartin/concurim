# Changelog

## 0.1.0 (unreleased)

First vertical slice, then the GUI-first milestone.

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
