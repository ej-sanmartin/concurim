import type { Point } from "../models/layout";
import { HAND_W, NODE_H, NODE_W, slotPoint } from "../models/layout";
import type { WorldState } from "../models/states";

/** Where things are right now (centers), including user-dragged positions. */
export interface Geometry {
  threads: Record<string, Point>;
  queues: Record<string, Point & { slots: number; w: number }>;
}

type Hands = Map<string, { i: number; n: number }>;

/** Index of each hand-held object among the objects at the same thread. */
export function handSlots(world: WorldState): Hands {
  const byThread = new Map<string, string[]>();
  for (const o of Object.values(world.objects)) {
    if ((o.phase === "held" || o.phase === "putting") && o.at) {
      byThread.set(o.at, [...(byThread.get(o.at) ?? []), o.id]);
    }
  }
  const out: Hands = new Map();
  for (const ids of byThread.values()) {
    ids.sort();
    ids.forEach((id, i) => out.set(id, { i, n: ids.length }));
  }
  return out;
}

/**
 * Where a data item is drawn: in its queue slot, in the hand of the thread
 * holding it, or just below the queue if it was discarded. ``null`` while it
 * does not exist yet. A pure function of the replayed state, so seeking
 * always lands on the same picture.
 */
export function objectPoint(
  id: string, world: WorldState, geo: Geometry, hands: Hands,
): Point | null {
  const o = world.objects[id];
  if (!o.at || o.phase === "new") return null;
  const queue = geo.queues[o.at];
  if (queue) {
    if (o.phase === "queued") {
      const idx = world.queues[o.at]?.items.indexOf(id) ?? -1;
      return idx < 0 ? null : slotPoint(queue, idx);
    }
    return { x: queue.x, y: queue.y + 90 }; // discarded
  }
  const t = geo.threads[o.at];
  if (!t) return null;
  const h = hands.get(id) ?? { i: 0, n: 1 };
  // Inside the node, in its right-hand strip; several items stack vertically.
  const gap = h.n > 1 ? Math.min(38, (NODE_H - 52) / (h.n - 1)) : 0;
  return {
    x: t.x + NODE_W / 2 - HAND_W / 2 - 4,
    y: t.y + (h.i - (h.n - 1) / 2) * gap,
  };
}
