import type { Replay } from "./replay";

export interface Point {
  x: number;
  y: number;
}

export interface Layout {
  width: number;
  height: number;
  threads: Record<string, Point & { role: Role }>;
  queues: Record<string, Point & { slots: number; w: number }>;
  edges: { thread: string; queue: string; dir: "put" | "get" }[];
  threadOrder: string[];
}

export type Role = "producer" | "consumer" | "stage" | "other";

export const NODE_W = 150;
export const NODE_H = 78;
const SLOT = 46;
const MAX_SLOTS = 8;
const GROUP_W = 230;
const PAD = 40;
const ROW = 134;

/**
 * Place threads and queues from *observed* operations only.
 *
 * A thread that gets from queue k is drawn right of it (stage k+1); one that
 * only puts is drawn at stage 0. Threads that touch no queue (for example a
 * coordinator that only joins) sit in a band above. Roles are labels derived
 * from observed operations, not from thread names.
 */
export function computeLayout(replay: Replay): Layout {
  const queueIds = Object.keys(replay.entities.queues);
  const qIndex = new Map(queueIds.map((q, i) => [q, i]));
  const gets = new Map<string, Set<string>>();
  const puts = new Map<string, Set<string>>();
  for (const ev of replay.events) {
    if (!ev.thread_id || !ev.resource_id || !qIndex.has(ev.resource_id)) continue;
    const bucket = ev.event_type.startsWith("queue.get.")
      ? gets
      : ev.event_type.startsWith("queue.put.")
        ? puts
        : null;
    if (!bucket) continue;
    if (!bucket.has(ev.thread_id)) bucket.set(ev.thread_id, new Set());
    bucket.get(ev.thread_id)!.add(ev.resource_id);
  }

  const stageOf = (t: string): number | null => {
    const g = gets.get(t);
    if (g) return 1 + Math.max(...[...g].map((q) => qIndex.get(q)!));
    return puts.has(t) ? 0 : null;
  };
  const roleOf = (t: string): Role => {
    const isGet = gets.has(t);
    const isPut = puts.has(t);
    if (isGet && isPut) return "stage";
    return isGet ? "consumer" : isPut ? "producer" : "other";
  };

  const nGroups = queueIds.length + 1;
  const slots = queueIds.map((q) => {
    const max = replay.entities.queues[q].maxsize;
    return max > 0 ? Math.min(max, MAX_SLOTS) : MAX_SLOTS - 2;
  });
  const queueW = slots.map((s) => s * SLOT + 24);
  const colX: number[] = [];
  const queueX: number[] = [];
  let x = PAD;
  for (let g = 0; g < nGroups; g++) {
    colX.push(x + GROUP_W / 2);
    x += GROUP_W;
    if (g < queueIds.length) {
      queueX.push(x + queueW[g] / 2 + 20);
      x += queueW[g] + 40;
    }
  }

  const groups: string[][] = Array.from({ length: nGroups }, () => []);
  const others: string[] = [];
  for (const t of Object.keys(replay.entities.threads)) {
    const s = stageOf(t);
    if (s === null) others.push(t);
    else groups[s].push(t);
  }
  const rows = Math.max(1, ...groups.map((g) => g.length));
  const bandH = others.length ? 120 : 0;
  const height = PAD + bandH + rows * ROW + PAD;

  const threads: Layout["threads"] = {};
  groups.forEach((g, gi) =>
    g.forEach((t, ti) => {
      const y = PAD + bandH + (rows * ROW) / 2 + (ti - (g.length - 1) / 2) * ROW;
      threads[t] = { x: colX[gi], y, role: roleOf(t) };
    }),
  );
  const totalW = x + PAD - 40;
  others.forEach((t, i) => {
    threads[t] = {
      x: totalW / 2 + (i - (others.length - 1) / 2) * (NODE_W + 30),
      y: PAD + 30,
      role: "other",
    };
  });

  const queues: Layout["queues"] = {};
  const qy = PAD + bandH + (rows * ROW) / 2;
  queueIds.forEach((q, i) => {
    queues[q] = { x: queueX[i], y: qy, slots: slots[i], w: queueW[i] };
  });

  const edges: Layout["edges"] = [];
  for (const [t, set] of puts) for (const q of set) edges.push({ thread: t, queue: q, dir: "put" });
  for (const [t, set] of gets) for (const q of set) edges.push({ thread: t, queue: q, dir: "get" });

  const threadOrder = [...groups.flat(), ...others];
  return { width: totalW, height, threads, queues, edges, threadOrder };
}

/** X/Y of the item slot ``index`` (0 = front, drawn at the right end). */
export function slotPoint(q: Point & { slots: number; w: number }, index: number): Point {
  const shown = Math.min(index, q.slots - 1);
  return { x: q.x + q.w / 2 - 12 - SLOT / 2 - shown * SLOT, y: q.y };
}

export const SLOT_SIZE = SLOT;
