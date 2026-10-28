# Cost

Measured on an Apple-silicon laptop, CPython 3.13
(`scripts/benchmark.py`):

| | |
| --- | --- |
| `TracedQueue` while not recording | ~2× a bare `queue.Queue` call (≈0.5 µs more) |
| Recording, detailed or light | ≈10 µs per put+get pair (≈20× a bare, work-free loop) |
| Memory while recording | ≈550 B/event (in-memory buffer) |
| Trace size | ≈19 B/event on disk (zip) |
| Load + replay | ≈1.5 s for 80k events |

The overhead matters when threads do no real work between instrumented
calls. With real work in between, it is usually small. Re-measure on
the machine you care about.
