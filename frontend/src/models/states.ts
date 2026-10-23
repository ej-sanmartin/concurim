import type {
  ObjectState,
  QueueState,
  Replay,
  SyncState,
  ThreadState,
} from "./replay";

/** The reconstructed world after applying events 0..i. */
export interface WorldState {
  threads: Record<string, ThreadState>;
  queues: Record<string, QueueState>;
  syncs: Record<string, SyncState>;
  objects: Record<string, ObjectState>;
}

export const EMPTY_WORLD: WorldState = {
  threads: {}, queues: {}, syncs: {}, objects: {},
};

/**
 * Fold frames into one world per event ("after event i"). Unchanged
 * entities are shared between consecutive worlds, so memory stays
 * proportional to the changes and any index is reachable in O(1) in either
 * direction (backward seeking is just a lookup).
 */
export function buildStates(replay: Replay): WorldState[] {
  const states: WorldState[] = [];
  let world = EMPTY_WORLD;
  for (const frame of replay.frames) {
    const { threads, queues, syncs, objects } = frame.changes;
    world = {
      threads: threads ? { ...world.threads, ...threads } : world.threads,
      queues: queues ? { ...world.queues, ...queues } : world.queues,
      syncs: syncs ? { ...world.syncs, ...syncs } : world.syncs,
      objects: objects ? { ...world.objects, ...objects } : world.objects,
    };
    states.push(world);
  }
  return states;
}

/** Binary search: index of the last event with timestamp <= tNs. */
export function indexAtTime(replay: Replay, tNs: number): number {
  const ev = replay.events;
  let lo = 0;
  let hi = ev.length - 1;
  let best = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (ev[mid].timestamp_ns <= tNs) {
      best = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return best;
}
