import { actorOf, type Replay } from "./replay";

export interface Point {
  x: number;
  y: number;
}

export interface Layout {
  width: number;
  height: number;
  threads: Record<string, Point & { role: Role }>;
  queues: Record<string, Point & { slots: number; w: number }>;
  syncs: Record<string, Point>;
  edges: { thread: string; queue: string; dir: "put" | "get" }[];
  /** Which threads/tasks use which lock, semaphore, event or condition. */
  syncEdges: { thread: string; sync: string }[];
  /** A condition and the lock it was created with. */
  syncLinks: { condition: string; lock: string }[];
  /** Worker groups big enough to collapse into one node. */
  groups: Group[];
  threadOrder: string[];
}

export interface Group extends Point {
  key: string;
  role: Role;
  members: string[];
}

export type Role = "producer" | "consumer" | "stage" | "other";

export const NODE_W = 210;
export const NODE_H = 100;
/** Right-hand strip of a worker node where the items it holds are drawn. */
export const HAND_W = 46;
export const SYNC_W = 190;
export const SYNC_H = 84;
export const GROUP_W_NODE = NODE_W;
export const GROUP_H_NODE = NODE_H;
/** Groups with at least this many members can be collapsed. */
export const GROUP_MIN = 4;
const SLOT = 46;
const MAX_SLOTS = 8;
const GROUP_W = 270;
const PAD = 40;
const ROW = 134;
const SYNC_BAND = 150;

type Touches = Map<string, Set<string>>;

const add = (m: Touches, key: string, value: string) => {
  if (!m.has(key)) m.set(key, new Set());
  m.get(key)!.add(value);
};

/** Operations on a sync resource that tie an actor to it. */
const touchesSync = (type: string) =>
  type.includes(".acquire.") || type.includes(".wait.") ||
  type === "event.set" || type === "event.cleared" ||
  type === "condition.notify" || type.startsWith("taskgroup.");

/** Conditions sit directly left of their lock, so the link is short. */
function orderSyncs(replay: Replay): string[] {
  const syncs = replay.entities.syncs ?? {};
  const ids = Object.keys(syncs);
  const lockOf = (id: string) => syncs[id].kind === "condition" ? syncs[id].lock : null;
  const attached = new Set(ids.filter((id) => lockOf(id) && lockOf(id)! in syncs));
  const out: string[] = [];
  for (const id of ids) {
    if (attached.has(id)) continue;
    for (const c of ids) if (lockOf(c) === id && attached.has(c)) out.push(c);
    out.push(id);
  }
  return out;
}

/** Which resource-bound operations each actor performed, from the events. */
function observeUse(replay: Replay) {
  const queues = new Set(Object.keys(replay.entities.queues));
  const syncs = new Set(Object.keys(replay.entities.syncs ?? {}));
  const gets: Touches = new Map();
  const puts: Touches = new Map();
  const locks: Touches = new Map();
  for (const ev of replay.events) {
    const actor = actorOf(ev);
    const rid = ev.resource_id;
    if (!actor || !rid) continue;
    const type = ev.event_type;
    if (syncs.has(rid)) {
      if (touchesSync(type)) add(locks, actor, rid);
      const child = ev.metadata?.child;
      if (type === "taskgroup.task.added" && child) add(locks, String(child), rid);
    } else if (queues.has(rid)) {
      if (type.startsWith("queue.get.") || type === "executor.task.started") add(gets, actor, rid);
      else if (type.startsWith("queue.put.") || type === "executor.submit") add(puts, actor, rid);
    }
  }
  return { gets, puts, locks };
}

/**
 * Place threads/tasks, queues (and executors) and locks from *observed*
 * operations only.
 *
 * An actor that gets from queue k is drawn right of it (stage k+1); one that
 * only puts is drawn at stage 0. Actors that touch no queue (for example a
 * coordinator that only joins, or tasks that only wait on locks) sit in a
 * band above; locks and semaphores sit in a band below. Roles are labels
 * derived from observed operations, not from names.
 */
export function computeLayout(replay: Replay): Layout {
  const queueIds = Object.keys(replay.entities.queues);
  const syncIds = orderSyncs(replay);
  const qIndex = new Map(queueIds.map((q, i) => [q, i]));
  const { gets, puts, locks } = observeUse(replay);

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
  const rows = Math.max(0, ...groups.map((g) => g.length));
  const bandH = others.length ? 120 : 0;
  const syncH = syncIds.length ? SYNC_BAND : 0;
  const height = PAD + bandH + rows * ROW + syncH + PAD;

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

  const syncs: Layout["syncs"] = {};
  const sy = PAD + bandH + rows * ROW + syncH / 2;
  syncIds.forEach((s, i) => {
    syncs[s] = { x: totalW / 2 + (i - (syncIds.length - 1) / 2) * (SYNC_W + 40), y: sy };
  });

  const edges: Layout["edges"] = [];
  for (const [t, set] of puts) for (const q of set) edges.push({ thread: t, queue: q, dir: "put" });
  for (const [t, set] of gets) for (const q of set) edges.push({ thread: t, queue: q, dir: "get" });
  const syncEdges: Layout["syncEdges"] = [];
  for (const [t, set] of locks) for (const s of set) syncEdges.push({ thread: t, sync: s });

  const syncLinks: Layout["syncLinks"] = syncIds.flatMap((id) => {
    const info = replay.entities.syncs[id];
    const lock = info.kind === "condition" ? info.lock : null;
    return lock && lock in replay.entities.syncs ? [{ condition: id, lock }] : [];
  });

  const bundles = [...groups.map((g, gi) => ({ key: `stage-${gi}`, members: g })),
    { key: "others", members: others }];
  const grouped: Group[] = bundles
    .filter((b) => b.members.length >= GROUP_MIN)
    .map((b) => {
      const at = b.members.map((t) => threads[t]);
      const mean = (f: (p: Point) => number) => at.reduce((a, p) => a + f(p), 0) / at.length;
      return { key: b.key, role: at[0].role, members: b.members, x: mean((p) => p.x), y: mean((p) => p.y) };
    });

  const threadOrder = [...groups.flat(), ...others];
  return {
    width: totalW, height, threads, queues, syncs, edges, syncEdges, syncLinks,
    groups: grouped, threadOrder,
  };
}

/** X/Y of the item slot ``index`` (0 = front, drawn at the right end). */
export function slotPoint(q: Point & { slots: number; w: number }, index: number): Point {
  const shown = Math.min(index, q.slots - 1);
  return { x: q.x + q.w / 2 - 12 - SLOT / 2 - shown * SLOT, y: q.y };
}

export const SLOT_SIZE = SLOT;
