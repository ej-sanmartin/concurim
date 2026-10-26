# Concurim documentation

What exists today, and the pages still to write. The
[README](../README.md) is the tour: install, record, and the viewer.

## Read these

| | |
| --- | --- |
| [README](../README.md) | Try it, observability levels, what a picture means |
| [Limitations](limitations.md) | What is observed, stuck programs, what is refused |
| [Trace format](trace-format.md) | The `.concurim` zip, for anyone building on the file |
| [Security](../SECURITY.md) | Local viewer, no telemetry, what a trace can contain |
| [Contributing](../CONTRIBUTING.md) | Tests, style, and how a PyPI upload will work |
| [Changelog](../CHANGELOG.md) | What 0.1.0 contains |

## Still to write

These are the pages to add as the tool settles. They are not written yet.

| Page | What it will cover |
| --- | --- |
| Getting started | `uvx concurim` once 0.1.0 is on PyPI, the first picture, five minutes |
| Concepts | One observed schedule, observed versus inferred, recording changes timing |
| Recording | Home screen, CLI, `record()`, when a `Traced*` primitive is worth it |
| Reading a run | Animation, Code, Timeline, lineage, resources, compare, export |
| Teaching | The samples: lock order, backpressure, pools, a GIL compare |

A program that cannot compile is not a run. A program that deadlocks is a
run that stops at the last observed event. Other interleavings are not
searched. Video captions, a live picture that keeps updating, and
a single HTML file you can send someone are listed in
[limitations](limitations.md) and are not in 0.1.0.
