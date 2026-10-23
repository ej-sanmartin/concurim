## What and why

## Checklist
- [ ] Tests use real threads and assert invariants, not one interleaving
- [ ] Inferred state is labelled inferred; unobservable behavior is not implied
- [ ] `docs/limitations.md` / `docs/trace-format.md` updated if behavior changed
- [ ] If the frontend changed: `scripts/build.sh` run and assets committed
- [ ] `uv run pytest`, `ruff`, `ty`, and `npm test` pass
