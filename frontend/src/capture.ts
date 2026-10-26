import { useEffect } from "react";

/** Views a video can show (same names as the viewer's modes). */
export type CaptureView = "animation" | "code" | "timeline" | "resources";

/** Options read from the URL when the exporter drives the viewer. */
export interface CaptureOptions {
  view: CaptureView;
  /** Panels shown on top of the picture: any of explanation, timeline. */
  overlays: Set<string>;
  /** Text burned into the footer; empty means no footer. */
  footer: string;
}

/** What the exporter calls (through Chrome DevTools) on the page. */
export interface CaptureBridge {
  ready: boolean;
  total: number;
  seek: (index: number) => Promise<void>;
}

declare global {
  interface Window { __concurim?: CaptureBridge }
}

const VIEWS: CaptureView[] = ["animation", "code", "timeline", "resources"];
const SETTLE_MS = 800;
const MAX_FRAMES = 120;

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
  };
}

/** Resolves after ``n`` animation frames, so the DOM has been painted. */
function frames(n: number): Promise<void> {
  return new Promise((done) => {
    const tick = (left: number) =>
      left <= 0 ? done() : requestAnimationFrame(() => tick(left - 1));
    tick(n);
  });
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
        for (let n = 0; n < MAX_FRAMES; n++) {
          await frames(1);
          const app = document.querySelector<HTMLElement>(".app");
          if (app?.dataset.index === String(i)) break;
        }
        await frames(2);
      },
    };
    window.__concurim = bridge;
    const id = window.setTimeout(() => { bridge.ready = true; }, SETTLE_MS);
    return () => {
      window.clearTimeout(id);
      delete window.__concurim;
    };
  }, [on, total, seek]);
}
