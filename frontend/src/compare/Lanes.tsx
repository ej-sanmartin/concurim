import type { RunSummary } from "../models/compare";

const W = 720;
const ROW = 14;
const MAX_LANES = 12;

/** Work spans per actor for each run, on one shared time scale. */
export function Lanes({ runs }: { runs: RunSummary[] }) {
  const scale = Math.max(...runs.map((r) => r.durationNs), 1);
  const x = (ns: number) => (ns / scale) * W;
  return (
    <div className="lanes" data-testid="compare-lanes">
      {runs.map((run) => {
        const shown = run.lanes.slice(0, MAX_LANES);
        return (
          <figure key={run.label}>
            <figcaption>
              {run.label} · {run.lanes.length} actor(s) with work
              {run.lanes.length > MAX_LANES && ` (first ${MAX_LANES} shown)`}
            </figcaption>
            <svg viewBox={`0 0 ${W} ${Math.max(shown.length, 1) * ROW + 14}`} width="100%"
              role="img" aria-label={`Work spans of ${run.label}`}>
              {shown.map((lane, i) => (
                <g key={lane.name} transform={`translate(0 ${i * ROW})`}>
                  <title>{lane.name}</title>
                  {lane.spans.map(([s, e]) => (
                    <rect key={`${s}-${e}`} className="lane-span" x={x(s)} y={2}
                      width={Math.max(x(e) - x(s), 1)} height={ROW - 4} rx="2" />
                  ))}
                </g>
              ))}
              <line className="lane-end" x1={x(run.durationNs)} x2={x(run.durationNs)}
                y1="0" y2={Math.max(shown.length, 1) * ROW + 10} />
            </svg>
          </figure>
        );
      })}
    </div>
  );
}
