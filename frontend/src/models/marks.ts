import { objectColor, STATUS_COLOR } from "../animations/palette";
import type { Replay } from "./replay";
import { actorOf } from "./replay";
import type { WorldState } from "./states";

/** Where one worker (thread, task or process) last was in the source. */
export interface Mark {
  actor: string;
  file: string;
  line: number;
  fn: string;
  /** The colour of the item it holds (its orb), else its status colour. */
  color: string;
  /** First and last line of the function it is in, when known. */
  range?: [number, number];
  /** ``line`` is a real position, not just where the function starts. */
  exact: boolean;
  /** Found by the background sampler, so approximate. */
  sampled: boolean;
}

interface Spot {
  index: number;
  file: string;
  line: number;
  fn: string;
  /** The worker finished a task here: nothing to show until the next one. */
  clear: boolean;
  sampled: boolean;
  range?: [number, number];
}

type Span = [number, number];

export type MarkIndex = Map<string, Spot[]>;

const CLEARS = new Set(["executor.task.finished", "executor.task.failed"]);
const ACTIVE = new Set(["running", "working", "waiting", "suspended"]);

/** The innermost function (first, last line) that contains ``line``. */
function enclosing(spans: Span[] | undefined, line: number): Span | undefined {
  let best: Span | undefined;
  for (const s of spans ?? []) {
    if (s[0] <= line && line <= s[1] && (!best || s[0] >= best[0])) best = s;
  }
  return best;
}

/**
 * Order a worker's spots in time (a sample comes after the event it follows)
 * and drop samples that arrive after its task finished: they were taken just
 * before the end and say nothing about the next task.
 */
function settle(list: Spot[]): Spot[] {
  list.sort((a, b) => a.index - b.index || Number(a.sampled) - Number(b.sampled));
  let cleared = false;
  return list.filter((s) => {
    if (s.sampled) return !cleared;
    cleared = s.clear;
    return true;
  });
}

/**
 * Per worker, the events and sampled lines that place it in an embedded
 * source file.
 */
export function buildMarkIndex(replay: Replay): MarkIndex {
  const files = new Set(replay.source_paths);
  const ranges = replay.code_ranges ?? {};
  const out: MarkIndex = new Map();
  const add = (who: string, spot: Spot) => {
    const list = out.get(who) ?? [];
    list.push(spot);
    out.set(who, list);
  };
  replay.events.forEach((e, index) => {
    const who = actorOf(e);
    if (!who) return;
    const clear = CLEARS.has(e.event_type);
    const s = e.source;
    if (!clear && !(s && files.has(s.file))) return;
    add(who, {
      index, clear, sampled: false, file: s?.file ?? "", line: s?.line ?? 0,
      fn: s?.function ?? "", range: s && enclosing(ranges[s.file], s.line),
    });
  });
  for (const s of replay.line_samples ?? []) {
    if (!files.has(s.file)) continue;
    add(s.actor, {
      index: s.at, clear: false, sampled: true, file: s.file, line: s.line,
      fn: s.function, range: enclosing(ranges[s.file], s.line),
    });
  }
  for (const [who, list] of out) out.set(who, settle(list));
  return out;
}

/** Last spot at or before ``i`` (binary search), or ``undefined``. */
function lastSpot(list: Spot[], i: number): Spot | undefined {
  let lo = 0;
  let hi = list.length - 1;
  let hit: Spot | undefined;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (list[mid].index <= i) { hit = list[mid]; lo = mid + 1; } else hi = mid - 1;
  }
  return hit;
}

/**
 * The workers that are active at event ``i`` and the source line each last
 * touched. A pool task starts at its function's first line (``exact`` is
 * false: show the whole body) until the line sampler sees it somewhere
 * inside; blocked calls and asyncio awaits are placed at the exact line.
 */
export function marksAt(index: MarkIndex, world: WorldState, i: number): Mark[] {
  const held = new Map<string, string>();
  for (const o of Object.values(world.objects)) {
    if ((o.phase === "held" || o.phase === "putting") && o.at) {
      const prev = held.get(o.at);
      if (prev === undefined || o.id < prev) held.set(o.at, o.id);
    }
  }
  const out: Mark[] = [];
  for (const [actor, list] of index) {
    const th = world.threads[actor];
    const spot = lastSpot(list, i);
    if (!th || !ACTIVE.has(th.status) || !spot || spot.clear) continue;
    const orb = held.get(actor);
    out.push({
      actor, file: spot.file, line: spot.line, fn: spot.fn,
      color: orb ? objectColor(orb) : STATUS_COLOR[th.status],
      range: spot.range, sampled: spot.sampled,
      exact: spot.sampled || !spot.range || spot.line !== spot.range[0],
    });
  }
  return out;
}

/** How strongly a line is shaded for a worker. */
export type Shade = "line" | "body" | "context";

/**
 * The shading of each line for the given marks: the exact line, the whole
 * body when the position inside it is unknown, or the faint surroundings of
 * an exact line.
 */
export function shadesByLine(marks: Mark[]): Map<number, { color: string; shade: Shade }[]> {
  const out = new Map<number, { color: string; shade: Shade }[]>();
  const add = (line: number, color: string, shade: Shade) =>
    out.set(line, [...(out.get(line) ?? []), { color, shade }]);
  for (const m of marks) {
    if (!m.range) add(m.line, m.color, "line");
    else {
      for (let l = m.range[0]; l <= m.range[1]; l++) {
        add(l, m.color, !m.exact ? "body" : l === m.line ? "line" : "context");
      }
    }
  }
  return out;
}
