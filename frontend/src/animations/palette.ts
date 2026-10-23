import type { ThreadStatus } from "../models/replay";

/** One consistent color per logical object, spread around the hue wheel. */
export function objectColor(objectId: string): string {
  const n = Number(objectId.split("-").pop()) || 0;
  const hue = (n * 47 + 200) % 360;
  return `hsl(${hue} 70% 58%)`;
}

export function objectLabel(objectId: string): string {
  return objectId.split("-").pop() ?? objectId;
}

export const STATUS_COLOR: Record<ThreadStatus, string> = {
  running: "var(--c-running)",
  waiting: "var(--c-waiting)",
  working: "var(--c-working)",
  finished: "var(--c-finished)",
  failed: "var(--c-failed)",
};

export const STATUS_LABEL: Record<ThreadStatus, string> = {
  running: "running",
  waiting: "waiting",
  working: "working",
  finished: "finished",
  failed: "failed",
};
