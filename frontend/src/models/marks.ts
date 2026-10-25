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
}

interface Spot {
  index: number;
  file: string;
  line: number;
  fn: string;
  /** The worker finished a task here: nothing to show until the next one. */
  clear: boolean;
}

export type MarkIndex = Map<string, Spot[]>;

const CLEARS = new Set(["executor.task.finished", "executor.task.failed"]);
const ACTIVE = new Set(["running", "working", "waiting", "suspended"]);

/** Per worker, the events that place it in an embedded source file. */
export function buildMarkIndex(replay: Replay): MarkIndex {
  const files = new Set(replay.source_paths);
  const out: MarkIndex = new Map();
  replay.events.forEach((e, index) => {
    const who = actorOf(e);
    if (!who) return;
    const clear = CLEARS.has(e.event_type);
    const s = e.source;
    if (!clear && !(s && files.has(s.file))) return;
    const list = out.get(who) ?? [];
    list.push({
      index, clear, file: s?.file ?? "", line: s?.line ?? 0, fn: s?.function ?? "",
    });
    out.set(who, list);
  });
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
 * touched. Pool tasks are placed at their function's first line (the
 * recorder does not trace line by line); blocked calls and asyncio awaits
 * are placed at the exact line.
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
    });
  }
  return out;
}
