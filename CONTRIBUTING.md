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

## Publishing

Pushing a version tag is what publishes to PyPI. The tag, `version` in
`pyproject.toml`, and `__version__` in `src/concurim/__init__.py` must
be the same number (`v1.0.0` for 1.0.0). PyPI rejects a repeated version.

One-time, at <https://pypi.org/manage/account/publishing/>, add a pending
publisher:

| Field | Value |
| --- | --- |
| PyPI project name | `concurim` |
| Owner | `ej-sanmartin` |
| Repository name | `concurim` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

No API token. Then, from a commit already on `main`:

```bash
git tag v1.0.0
git push origin v1.0.0
```

`.github/workflows/release.yml` builds the package, uploads it, and opens
the GitHub release. Do not also upload that version with twine or
`uv publish`.

Check a build locally with `scripts/build.sh` and `scripts/smoke_wheel.sh`.
Once the version is on PyPI: `uvx concurim` (home screen; the server
copies itself onto the interpreter you pick) and `uv add --dev concurim`
when `concurim record` must import the project.

## Frontend development note

`npm run dev` proxies `/api` to the server, but POST features (opening
examples, dropping files, running programs) fail there: they need the
per-launch token the real server embeds only in the HTML it serves. For those, run `npm run build` and use `uv run concurim`.
Playwright starts two servers (`concurim demo` on 8799, the home screen on
8798) via `uv run`.
