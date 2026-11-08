import type { Hazard, Replay } from "../models/replay";

interface Props {
  replay: Replay;
  /** Show the event a fail state was found at. */
  onSeek: (i: number) => void;
}

/** One fail state, with a jump to the event it showed up at. */
function HazardRow({ h, onSeek }: { h: Hazard; onSeek: (i: number) => void }) {
  return (
    <p className="warning" data-testid="hazard" data-kind={h.kind}>
      ⚠ {h.text}{" "}
      <button className="link" onClick={() => onSeek(h.at)}>
        event {h.at + 1}
      </button>
    </p>
  );
}

/** What was recorded, the environment, and what Concurim cannot see. */
export function TraceInfo({ replay, onSeek }: Props) {
  const m = replay.metadata;
  const hazards = replay.hazards ?? [];
  // Hazards are also in ``warnings`` as one line each; show them once, below.
  const plain = replay.warnings.filter((w) => !hazards.some((h) => w.endsWith(h.text)));
  const seen = hazards.filter((h) => !h.inferred);
  const patterns = hazards.filter((h) => h.inferred);
  const env = m.environment ?? {};
  const cov = m.coverage ?? { observed: [], not_observed: [] };
  return (
    <div className="info" data-testid="trace-info">
      {plain.map((w) => (
        <p key={w} className="warning">⚠ {w}</p>
      ))}
      {seen.length > 0 && <h4>Found in this run</h4>}
      {seen.map((h) => <HazardRow key={h.text} h={h} onSeek={onSeek} />)}
      {patterns.length > 0 && <h4>Patterns, inferred</h4>}
      {patterns.length > 0 && (
        <p className="muted">
          These rest on history or a pattern, not on a block that happened.
          Concurim does not search other schedules.
        </p>
      )}
      {patterns.map((h) => <HazardRow key={h.text} h={h} onSeek={onSeek} />)}
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
