# Contributing

Thanks for helping! Concurim values **accuracy over spectacle**: a visualization
must follow recorded events, and anything inferred must be labelled.

## Setup

```bash
uv sync
uv run pytest && uv run ruff check . && uv run ruff format --check . \
  && uv run ty check src
cd frontend && npm ci && npm test
```

The compiled viewer lives in `src/concurim/viewer/static` and is committed so
the package works without Node. After frontend changes run
`scripts/build.sh` and commit the result (CI fails if it is stale).
Regenerate frontend fixtures with `uv run python scripts/make_fixtures.py`
(real capture; then refresh Playwright snapshots with
`npx playwright test --update-snapshots`).

## Adding an instrumented primitive

1. Add event types in `recorder/events.py` and to the JSON Schema.
2. Wrap the primitive in `instrumentation/`. Emit state-changing events at the
   point where the real state changes (under the primitive's own lock if the
   primitive offers a hook); use `mark_internal(__file__)` for source
   attribution; never take locks that could invert with the collector's.
3. Add a reducer handler in `replay/state.py` and a rule in `replay/rules_*.py`.
4. Test with real threads. Never assert one incidental interleaving; assert
   invariants and use events/barriers to force the situation you test.
5. Update `docs/limitations.md`.

## Style

Google style, 80 columns (hard limit 100), a short docstring per function,
files under ~300 lines (split before they grow), no duplicated logic.
Prefer the simplest design; do not add dependencies lightly (runtime
dependencies are currently zero).
