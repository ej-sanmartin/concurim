import type { WorldState } from "./states";

export type EdgeKind = "holds" | "waits" | "member";

/** One relation between an actor and a resource at the current moment. */
export interface ResourceEdge {
  actor: string;
  resource: string;
  kind: EdgeKind;
  label: string;
  /** Part of a circular wait between locks. */
  cycle: boolean;
}

export interface ResourceGraph {
  actors: string[];
  resources: string[];
  edges: ResourceEdge[];
  /** Actors that wait on each other in a circle (locks only). */
  cycle: string[];
}

const EXCLUSIVE = new Set(["lock", "rlock"]);

/**
 * Actors in a circle, each waiting for a lock held by the next one. Every
 * actor waits on at most one thing, so following `next` pointers is enough.
 */
function findCycle(next: Map<string, string>): Set<string> {
  const done = new Set<string>();
  const found = new Set<string>();
  for (const start of next.keys()) {
    const path: string[] = [];
    const at = new Map<string, number>();
    let cur: string | undefined = start;
    while (cur !== undefined && !done.has(cur) && !at.has(cur)) {
      at.set(cur, path.length);
      path.push(cur);
      cur = next.get(cur);
    }
    if (cur !== undefined && at.has(cur)) {
      for (const a of path.slice(at.get(cur)!)) found.add(a);
    }
    for (const a of path) done.add(a);
  }
  return found;
}

/**
 * Who holds and who waits for what, right now, from the replayed state.
 *
 * Holds come from locks and semaphores; waits from each actor's recorded
 * `waiting_on`; task groups add membership. A cycle is reported only for
 * exclusive locks: waiting for a semaphore permit does not prove that a
 * particular holder is the one being waited for.
 */
export function buildResourceGraph(world: WorldState): ResourceGraph {
  const actors = Object.keys(world.threads);
  const resources = [...Object.keys(world.queues), ...Object.keys(world.syncs)];
  const known = new Set(resources);
  const edges: ResourceEdge[] = [];

  for (const s of Object.values(world.syncs)) {
    const counts = new Map<string, number>();
    for (const h of s.holders) counts.set(h, (counts.get(h) ?? 0) + 1);
    for (const [actor, n] of counts) {
      edges.push({ actor, resource: s.id, kind: "holds", cycle: false,
        label: n > 1 ? `holds ×${n}` : "holds" });
    }
    if (s.kind === "taskgroup") {
      for (const m of s.members) {
        if (m in world.threads) {
          edges.push({ actor: m, resource: s.id, kind: "member", label: "member", cycle: false });
        }
      }
    }
  }
  const next = new Map<string, string>();
  const awaited = new Map<string, string>();
  for (const t of Object.values(world.threads)) {
    const w = t.waiting_on;
    if (!w || !known.has(w.resource)) continue;
    edges.push({ actor: t.id, resource: w.resource, kind: "waits", label: w.op, cycle: false });
    const lock = world.syncs[w.resource];
    const owner = lock && EXCLUSIVE.has(lock.kind)
      ? lock.holders.find((h) => h !== t.id) : undefined;
    if (owner) { next.set(t.id, owner); awaited.set(t.id, w.resource); }
  }
  const loop = findCycle(next);
  const loopLocks = new Set([...loop].map((a) => awaited.get(a)));
  for (const e of edges) {
    e.cycle = loop.has(e.actor) && loopLocks.has(e.resource) && e.kind !== "member";
  }
  return { actors, resources, edges, cycle: [...loop] };
}
