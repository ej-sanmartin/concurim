import type { TraceEvent } from "./replay";

/** A pattern must repeat at least this many times in a row to be folded. */
export const FOLD_MIN = 3;
/** Longest repeating pattern, in events (a worker loop is a few events). */
export const MAX_PERIOD = 6;

export interface FoldedRow {
  /** Index into the event list. */
  index: number;
  /** Set on the first row of a folded run. */
  fold?: { repeats: number; period: number; open: boolean };
}

const key = (e: TraceEvent) => `${e.event_type}|${e.resource_id ?? ""}`;

/** Repetitions of the ``period`` events starting at ``at`` (>= 1). */
function repeatsAt(keys: string[], at: number, period: number): number {
  let reps = 1;
  for (;;) {
    const next = at + reps * period;
    if (next + period > keys.length) return reps;
    for (let j = 0; j < period; j++) {
      if (keys[at + j] !== keys[next + j]) return reps;
    }
    reps++;
  }
}

/**
 * Fold repeating patterns of events (the same few types on the same
 * resources, over and over: a worker loop, forty ``thread.started``) into
 * one row showing the first event and a repeat count. A run stays open when
 * the user opened it or the playhead is inside it, so the current event is
 * never hidden.
 */
export function foldRows(
  events: TraceEvent[], indices: number[], open: ReadonlySet<number>, current: number,
): FoldedRow[] {
  const keys = indices.map((i) => key(events[i]));
  const out: FoldedRow[] = [];
  let at = 0;
  while (at < indices.length) {
    let folded = false;
    for (let period = 1; period <= MAX_PERIOD && !folded; period++) {
      const repeats = repeatsAt(keys, at, period);
      if (repeats < FOLD_MIN) continue;
      const run = indices.slice(at, at + repeats * period);
      const isOpen = open.has(run[0]) || run.includes(current);
      out.push({ index: run[0], fold: { repeats, period, open: isOpen } });
      if (isOpen) run.slice(1).forEach((index) => out.push({ index }));
      at += run.length;
      folded = true;
    }
    if (!folded) out.push({ index: indices[at++] });
  }
  return out;
}
