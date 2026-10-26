import type { Replay } from "./replay";

/** One line of a lineage tree. */
export interface LineageRow {
  id: string;
  depth: number;
  /** False when a parent id was recorded for an item that never appears. */
  known: boolean;
  /** True for the focused item, its ancestors and its descendants. */
  related: boolean;
}

/** Parent of an item from the explicit `derived_from` annotation. */
const parentOf = (replay: Replay, id: string): string | null =>
  replay.entities.objects[id]?.parent ?? null;

/** Ancestors of `id`, nearest first. Stops on a cycle or a missing link. */
export function ancestors(replay: Replay, id: string): string[] {
  const out: string[] = [];
  const seen = new Set([id]);
  for (let p = parentOf(replay, id); p && !seen.has(p); p = parentOf(replay, p)) {
    out.push(p);
    seen.add(p);
  }
  return out;
}

/** Child ids per parent id, in the order the children were created. */
function childMap(replay: Replay): Map<string, string[]> {
  const kids = new Map<string, string[]>();
  for (const o of Object.values(replay.entities.objects)) {
    if (!o.parent) continue;
    if (!kids.has(o.parent)) kids.set(o.parent, []);
    kids.get(o.parent)!.push(o.id);
  }
  return kids;
}

/** Items that have at least one recorded parent or child. */
export function hasLineage(replay: Replay): boolean {
  return Object.values(replay.entities.objects).some((o) => o.parent);
}

/** The oldest known ancestor of `id` (`id` itself when it has none). */
export function rootOf(replay: Replay, id: string): string {
  const up = ancestors(replay, id);
  return up.length ? up[up.length - 1] : id;
}

/** Roots of every chain with at least two links, in creation order. */
export function lineageRoots(replay: Replay): string[] {
  const kids = childMap(replay);
  const roots = new Set<string>();
  for (const id of kids.keys()) roots.add(rootOf(replay, id));
  return [...roots];
}

/** Items a viewer should walk through when `id` is the focus. */
function related(replay: Replay, id: string, kids: Map<string, string[]>) {
  const out = new Set([id, ...ancestors(replay, id)]);
  const stack = [id];
  while (stack.length) {
    for (const c of kids.get(stack.pop()!) ?? []) {
      if (!out.has(c)) { out.add(c); stack.push(c); }
    }
  }
  return out;
}

/** The whole family tree containing `focus`, depth first from its root. */
export function familyRows(replay: Replay, focus: string): LineageRow[] {
  const kids = childMap(replay);
  const near = related(replay, focus, kids);
  const rows: LineageRow[] = [];
  const seen = new Set<string>();
  const walk = (id: string, depth: number) => {
    if (seen.has(id)) return;
    seen.add(id);
    rows.push({ id, depth, known: id in replay.entities.objects, related: near.has(id) });
    for (const c of kids.get(id) ?? []) walk(c, depth + 1);
  };
  walk(rootOf(replay, focus), 0);
  return rows;
}
