import type { TraceEvent } from "../models/replay";

/** Events that leave no visible mark on the canvas play back quickly. */
const QUICK = new Set([
  "thread.registered",
  "thread.start.requested",
  "queue.put.started",
  "queue.get.started",
  "queue.created",
]);

export const BASE_DELAY_MS = 620;
export const QUICK_DELAY_MS = 110;

/** Wall-clock milliseconds to dwell on ``ev`` at playback ``speed``. */
export function stepDelay(ev: TraceEvent | undefined, speed: number): number {
  const base = ev && QUICK.has(ev.event_type) ? QUICK_DELAY_MS : BASE_DELAY_MS;
  return base / speed;
}

export function clampIndex(i: number, total: number): number {
  return Math.max(0, Math.min(total - 1, Math.round(i)));
}

export const SPEEDS = [0.25, 0.5, 1, 2, 4, 8];
