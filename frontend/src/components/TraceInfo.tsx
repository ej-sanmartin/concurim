import type { Replay } from "../models/replay";

/** What was recorded, the environment, and what Concurim cannot see. */
export function TraceInfo({ replay }: { replay: Replay }) {
  const m = replay.metadata;
  const env = m.environment ?? {};
  const cov = m.coverage ?? { observed: [], not_observed: [] };
  return (
    <div className="info" data-testid="trace-info">
      {replay.warnings.map((w) => (
        <p key={w} className="warning">⚠ {w}</p>
      ))}
      <h4>Environment</h4>
      <p>
        {env.implementation} {env.python_version} · {env.platform}{" "}
        {env.machine}
        <br />
        free-threaded build: {String(env.free_threaded_build)} · GIL enabled
        at runtime: {String(env.gil_enabled)}
      </p>
      <h4>Observed</h4>
      <ul>{(cov.observed as string[]).map((t) => <li key={t}>{t}</li>)}</ul>
      <h4>Not observed</h4>
      <ul>{(cov.not_observed as string[]).map((t) => <li key={t}>{t}</li>)}</ul>
      <p className="muted">
        Traces can contain paths, names and, if enabled, source and payload
        previews. Review before sharing. Recording can alter timing.
      </p>
    </div>
  );
}
