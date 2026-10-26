/**
 * A clock the exporter winds by hand, so tweens are reproducible.
 *
 * In capture mode (``?capture=...``) ``performance.now`` and
 * ``requestAnimationFrame`` are replaced: time moves only when ``advance``
 * is called, and every queued frame callback then runs once. Motion reads
 * both at module load, so this file must be the first import of the app.
 * Outside capture mode nothing is touched.
 */

let now = 0;
let nextId = 0;
let queue: [number, FrameRequestCallback][] = [];
let installed = false;

/** Move the fake clock forward and run the frame callbacks that were due. */
export function advanceClock(ms: number): void {
  now += ms;
  const due = queue;
  queue = [];
  for (const [, callback] of due) callback(now);
}

/** Whether the fake clock is in use. */
export const clockInstalled = (): boolean => installed;

/** Replace the time sources when the URL asks for capture mode. */
export function installCaptureClock(search: string): boolean {
  if (typeof window === "undefined" || !search.includes("capture")) return false;
  if (!new URLSearchParams(search).has("capture")) return false;
  performance.now = () => now;
  window.requestAnimationFrame = (callback) => {
    queue.push([++nextId, callback]);
    return nextId;
  };
  window.cancelAnimationFrame = (id) => {
    queue = queue.filter(([queued]) => queued !== id);
  };
  installed = true;
  return true;
}

if (typeof window !== "undefined") installCaptureClock(window.location.search);
