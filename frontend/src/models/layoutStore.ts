// Remembering where the user dragged nodes and what they chose to hide.
// Purely visual preferences, kept in this browser's localStorage only.

import type { Point } from "./layout";
import type { Replay } from "./replay";

const LAYOUT_PREFIX = "concurim-layout:";
const HIDDEN_KEY = "concurim-hidden";

/** Same program + same set of threads/queues => same remembered layout. */
export function layoutKey(replay: Replay): string {
  const names = (o: Record<string, { name: string }>) =>
    Object.values(o).map((e) => e.name).sort().join(",");
  const script = replay.metadata.program?.script ?? "trace";
  return `${LAYOUT_PREFIX}${script}|${names(replay.entities.threads)}|${names(replay.entities.queues)}`;
}

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable or full: preferences are best-effort */
  }
}

/** Saved node centers; only finite numbers are accepted. */
export function loadPositions(key: string): Record<string, Point> {
  const raw = read<Record<string, Point>>(key, {});
  const out: Record<string, Point> = {};
  for (const [id, p] of Object.entries(raw)) {
    if (Number.isFinite(p?.x) && Number.isFinite(p?.y)) out[id] = { x: p.x, y: p.y };
  }
  return out;
}

export const savePositions = (key: string, positions: Record<string, Point>) =>
  write(key, positions);

export function clearPositions(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

export const loadHidden = (): string[] => read<string[]>(HIDDEN_KEY, []);
export const saveHidden = (hidden: string[]) => write(HIDDEN_KEY, hidden);
