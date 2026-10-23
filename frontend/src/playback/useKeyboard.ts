import { useEffect } from "react";
import type { Playback } from "./usePlayback";
import { SPEEDS } from "./stepping";

export interface KeyActions {
  /** Jump to the next (1) or previous (-1) blocking event. */
  blocking: (dir: 1 | -1) => void;
  /** Jump to the next/previous event of the selected resource. */
  selection: (dir: 1 | -1) => void;
  fit: () => void;
}

/**
 * Space play/pause, arrows step (Shift = 10), Home/End, [ ] speed,
 * b/B next/previous blocking event, n/N next/previous event for the
 * selection, f fit the graph to the view.
 */
export function useKeyboard(pb: Playback, total: number, act: KeyActions): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const jump = e.shiftKey ? 10 : 1;
      const dir = e.shiftKey ? -1 : 1;
      const speedIdx = SPEEDS.indexOf(pb.speed);
      switch (e.key) {
        case " ": pb.toggle(); break;
        case "ArrowRight": pb.step(jump); break;
        case "ArrowLeft": pb.step(-jump); break;
        case "Home": pb.seek(0); break;
        case "End": pb.seek(total - 1); break;
        case "]": pb.setSpeed(SPEEDS[Math.min(SPEEDS.length - 1, speedIdx + 1)]); break;
        case "[": pb.setSpeed(SPEEDS[Math.max(0, speedIdx - 1)]); break;
        case "b": case "B": act.blocking(dir); break;
        case "n": case "N": act.selection(dir); break;
        case "f": act.fit(); break;
        default: return;
      }
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pb, total, act]);
}
