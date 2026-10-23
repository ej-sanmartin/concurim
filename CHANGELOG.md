# Changelog

## 0.1.0 (unreleased)

First vertical slice.

- `TracedQueue` (`queue.Queue` subclass), `TracedThread`, `work()` spans,
  explicit lineage, `record()` API.
- `.concurim` trace format with JSON Schema, bounded buffer, truncation flag,
  optional embedded source and payload previews.
- Replay engine with per-event state, blocking/join/shutdown handling, and
  rule-based explanations that separate observed from inferred.
- Local viewer: animated producer/queue/consumer canvas, timeline with
  spans and occupancy, playback controls, source panel, inspector, event log.
- CLI: `record`, `view`, `demo`, `inspect`.
