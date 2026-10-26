import { useEffect } from "react";
import { advanceClock } from "./captureClock";

/** Views a video can show (same names as the viewer's modes). */
export type CaptureView = "animation" | "code" | "timeline" | "resources";

/** Options read from the URL when the exporter drives the viewer. */
export interface CaptureOptions {
  view: CaptureView;
  /** Panels shown on top of the picture: any of explanation, timeline. */
  overlays: Set<string>;
  /** Text burned into the footer; empty means no footer. */
  footer: string;
  /** How long the glide between two events lasts, in milliseconds. */
  motionMs: number;
}

/** What the exporter calls (through Chrome DevTools) on the page. */
export interface CaptureBridge {
  ready: boolean;
  total: number;
  /** Show an event (no time passes: its tweens are at their start). */
  seek: (index: number) => Promise<void>;
  /** Let ``ms`` of animation time pass, exactly. */
  advance: (ms: number) => void;
  /** Run every animation to its end. */
  settle: () => void;
}

declare global {
  interface Window { __concurim?: CaptureBridge }
}

const VIEWS: CaptureView[] = ["animation", "code", "timeline", "resources"];
const READY_MS = 800;
const MAX_POLLS = 200;
const SETTLE_MS = 2000;
const STEP_MS = 1000 / 60;

/**
 * Capture options from a query string, or null in normal use.
 *
 * Capture mode is how videos stay deterministic: the exporter chooses the
 * event, the page shows exactly that state with no tweens or looping
 * animation, and a screenshot is taken. No timer decides what is on screen.
 */
export function readCapture(search: string): CaptureOptions | null {
  const q = new URLSearchParams(search);
  if (!q.has("capture")) return null;
  const view = q.get("view") as CaptureView;
  return {
    view: VIEWS.includes(view) ? view : "animation",
    overlays: new Set((q.get("overlays") ?? "").split(",").filter(Boolean)),
    footer: (q.get("footer") ?? "").slice(0, 200),
    motionMs: Math.min(2000, Math.max(0, Number(q.get("motion") ?? 0) || 0)),
  };
}

const elapsed = new WeakMap<Animation, number>();

/** Wait a real moment (rendering is asynchronous; time is not involved). */
const pause = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Advance the fake clock and pin every CSS/Web animation to its new time. */
function advance(ms: number): void {
  advanceClock(ms);
  for (const animation of document.getAnimations()) {
    const t = (elapsed.get(animation) ?? 0) + ms;
    elapsed.set(animation, t);
    animation.pause();
    animation.currentTime = t;
  }
}

/** Run everything to its end, then drop finished animations. */
function settle(): void {
  for (let t = 0; t < SETTLE_MS; t += STEP_MS) advance(STEP_MS);
  for (const animation of document.getAnimations()) {
    try { animation.finish(); } catch { /* infinite: not used in capture */ }
  }
}

/**
 * Expose ``window.__concurim`` while capturing. ``seek`` resolves only once
 * the page reports the requested event as rendered. ``ready`` turns true
 * after the first fit of the graph has settled.
 */
export function useCaptureBridge(
  on: boolean, total: number, seek: (i: number) => void,
): void {
  useEffect(() => {
    if (!on) return;
    const bridge: CaptureBridge = {
      ready: false,
      total,
      seek: async (i) => {
        seek(i);
        for (let n = 0; n < MAX_POLLS; n++) {
          await pause(5);
          const app = document.querySelector<HTMLElement>(".app");
          if (app?.dataset.index === String(i)) break;
        }
        await pause(40);
        document.body.getBoundingClientRect(); // start CSS transitions now
        advanceClock(0); // let Motion start its tweens at t = 0
      },
      advance,
      settle,
    };
    window.__concurim = bridge;
    const id = window.setTimeout(() => { bridge.ready = true; }, READY_MS);
    return () => {
      window.clearTimeout(id);
      delete window.__concurim;
    };
  }, [on, total, seek]);
}
