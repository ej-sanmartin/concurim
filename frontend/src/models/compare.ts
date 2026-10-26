import type { Replay } from "./replay";

/** One actor's observed work, as intervals in nanoseconds. */
export interface Lane {
  name: string;
  spans: [number, number][];
}

/** What can honestly be said about one recording. */
export interface RunSummary {
  label: string;
  script: string | null;
  python: string;
  implementation: string;
  platform: string;
  freeThreaded: boolean | null;
  gilEnabled: boolean | null;
  durationNs: number;
  events: number;
  lanes: Lane[];
  /** Sum of all observed work-span lengths. */
  busyNs: number;
  /** Most work spans open at the same moment. */
  maxOverlap: number;
}

/** Observed work: spans marked with `work()` or run by a pool worker. */
export function summarize(replay: Replay, label: string): RunSummary {
  const m = replay.metadata;
  const env = m.environment ?? {};
  const at = (i: number) => replay.events[Math.min(i, replay.events.length - 1)]?.timestamp_ns ?? 0;
  const byActor = new Map<string, [number, number][]>();
  const edges: [number, number][] = [];
  for (const s of replay.spans) {
    if (s.kind !== "work" || !s.thread) continue;
    const span: [number, number] = [at(s.start), at(s.end)];
    if (!byActor.has(s.thread)) byActor.set(s.thread, []);
    byActor.get(s.thread)!.push(span);
    edges.push([span[0], 1], [span[1], -1]);
  }
  // At equal times, closings sort first so touching spans do not overlap.
  edges.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  let open = 0;
  let maxOverlap = 0;
  for (const [, d] of edges) {
    open += d;
    maxOverlap = Math.max(maxOverlap, open);
  }
  const lanes = [...byActor].map(([id, spans]) => ({
    name: replay.entities.threads[id]?.name ?? id, spans,
  }));
  return {
    label,
    script: m.program?.script ?? null,
    python: env.python_version ?? "?",
    implementation: env.implementation ?? "Python",
    platform: [env.platform, env.machine].filter(Boolean).join(" "),
    freeThreaded: env.free_threaded_build ?? null,
    gilEnabled: env.gil_enabled ?? null,
    durationNs: replay.summary.duration_ns,
    events: replay.events.length,
    lanes,
    busyNs: lanes.reduce((n, l) => n + l.spans.reduce((k, [a, b]) => k + (b - a), 0), 0),
    maxOverlap,
  };
}

const gil = (r: RunSummary) =>
  r.gilEnabled === null ? "GIL state unknown" : r.gilEnabled ? "GIL enabled" : "GIL disabled";

/** Plain-language differences between two runs; never claims causes. */
export function describeDifferences(a: RunSummary, b: RunSummary): string[] {
  const out: string[] = [];
  if (a.script && b.script && a.script !== b.script) {
    out.push(`These come from different programs (${a.script} and ${b.script}); `
      + "differences may not be about the interpreter.");
  }
  if (a.durationNs > 0 && b.durationNs > 0) {
    const ratio = a.durationNs / b.durationNs;
    if (ratio > 1.05 || ratio < 1 / 1.05) {
      const [fast, slow, x] = ratio > 1 ? [b, a, ratio] : [a, b, 1 / ratio];
      out.push(`${fast.label} took ${(fast.durationNs / 1e9).toFixed(2)}s, `
        + `${x.toFixed(2)}× faster than ${slow.label} (${(slow.durationNs / 1e9).toFixed(2)}s).`);
    } else {
      out.push("The two recordings took about the same wall time.");
    }
  }
  if (gil(a) !== gil(b) || a.python !== b.python) {
    out.push(`${a.label}: Python ${a.python}, ${gil(a)}. ${b.label}: Python ${b.python}, ${gil(b)}.`);
  }
  if (a.maxOverlap !== b.maxOverlap) {
    out.push(`Observed work overlapped at most ${a.maxOverlap}-fold in ${a.label} `
      + `and ${b.maxOverlap}-fold in ${b.label}.`);
  }
  if (a.busyNs === 0 || b.busyNs === 0) {
    out.push("A recording without work spans cannot show overlap; mark work with "
      + "work() or use a pool.");
  }
  return out;
}
