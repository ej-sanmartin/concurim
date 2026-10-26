import type { TraceEvent } from "../models/replay";

/** How playback is paced. */
export type Pace = "explain" | "realtime";

/** Events that leave no visible mark on the canvas play back quickly. */
const QUICK = new Set([
  "thread.registered",
  "thread.start.requested",
  "queue.put.started",
  "queue.get.started",
  "queue.created",
  "lock.created",
  "lock.acquire.started",
  "semaphore.created",
  "semaphore.acquire.started",
  "event.created",
  "event.wait.started",
  "condition.created",
  "taskgroup.created",
  "executor.created",
]);

export const BASE_DELAY_MS = 620;
export const QUICK_DELAY_MS = 110;
/** Synchronization events worth dwelling on: blocking and shutdown. */
export const EMPHASIS_DELAY_MS = 1000;
/** Real-time pacing: smallest dwell, and the cap used to compress idle time. */
export const MIN_REAL_DELAY_MS = 16;
export const IDLE_CAP_MS = 400;

const isEmphasized = (type: string) =>
  type.endsWith(".blocked") || type.includes("shutdown");

/**
 * Explanatory pacing: a steady beat per event, longer for the events that
 * teach the most (blocking, shutdown), shorter for ones with no visual effect.
 */
export function stepDelay(ev: TraceEvent | undefined, speed: number): number {
  const type = ev?.event_type ?? "";
  const base = QUICK.has(type)
    ? QUICK_DELAY_MS
    : isEmphasized(type) ? EMPHASIS_DELAY_MS : BASE_DELAY_MS;
  return base / speed;
}

/**
 * Recorded-time pacing: dwell for the real gap before ``next``. With
 * ``compress`` an idle gap longer than ``IDLE_CAP_MS`` is shortened to it, so
 * a long sleep does not stall the replay.
 */
export function realDelay(
  prev: TraceEvent, next: TraceEvent, speed: number, compress: boolean,
): number {
  const gap = Math.max(0, (next.timestamp_ns - prev.timestamp_ns) / 1e6);
  const shown = compress ? Math.min(gap, IDLE_CAP_MS) : gap;
  return Math.max(MIN_REAL_DELAY_MS, shown / speed);
}

/** Wall-clock milliseconds to wait before showing event ``i + 1``. */
export function delayBefore(
  events: TraceEvent[], i: number, speed: number, pace: Pace, compress: boolean,
): number {
  return pace === "realtime"
    ? realDelay(events[i], events[i + 1], speed, compress)
    : stepDelay(events[i + 1], speed);
}

export function clampIndex(i: number, total: number): number {
  return Math.max(0, Math.min(total - 1, Math.round(i)));
}

export const SPEEDS = [0.25, 0.5, 1, 2, 4, 8];
