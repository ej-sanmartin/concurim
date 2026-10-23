import type { Replay } from "./replay";

/** Display name for a thread, task, queue, executor, lock or semaphore id. */
export function nameOf(replay: Replay, id: string | null | undefined): string {
  if (!id) return "–";
  const e = replay.entities;
  return e.threads[id]?.name ?? e.queues[id]?.name ?? e.syncs?.[id]?.name ?? id;
}
