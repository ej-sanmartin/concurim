import type { TraceEvent } from "../models/replay";
import type { Selection } from "../models/selection";

/** An event where a thread started waiting (put/get blocked on a queue). */
export const isBlocking = (ev: TraceEvent): boolean =>
  ev.event_type.endsWith(".blocked");

/** Whether ``ev`` involves the selected thread, queue or object. */
export function matchesSelection(ev: TraceEvent, sel: NonNullable<Selection>): boolean {
  if (sel.kind === "thread") return ev.thread_id === sel.id;
  if (sel.kind === "queue") return ev.resource_id === sel.id;
  return ev.object_id === sel.id;
}

/**
 * Nearest event after (``dir`` = 1) or before (-1) ``from`` that satisfies
 * ``test``; ``null`` when there is none.
 */
export function findEvent(
  events: TraceEvent[], from: number, dir: 1 | -1,
  test: (ev: TraceEvent) => boolean,
): number | null {
  for (let i = from + dir; i >= 0 && i < events.length; i += dir) {
    if (test(events[i])) return i;
  }
  return null;
}

export const nextBlocking = (events: TraceEvent[], from: number, dir: 1 | -1 = 1) =>
  findEvent(events, from, dir, isBlocking);

export const nextForSelection = (
  events: TraceEvent[], from: number, sel: Selection, dir: 1 | -1 = 1,
) => (sel ? findEvent(events, from, dir, (e) => matchesSelection(e, sel)) : null);
