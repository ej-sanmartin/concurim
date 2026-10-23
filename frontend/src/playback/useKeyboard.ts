import { useEffect } from "react";
import type { Playback } from "./usePlayback";
import { SPEEDS } from "./stepping";

/** Space = play/pause, arrows = step, Shift+arrows = 10, Home/End, [ ] speed. */
export function useKeyboard(pb: Playback, total: number): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const jump = e.shiftKey ? 10 : 1;
      const speedIdx = SPEEDS.indexOf(pb.speed);
      switch (e.key) {
        case " ":
          pb.toggle();
          break;
        case "ArrowRight":
          pb.step(jump);
          break;
        case "ArrowLeft":
          pb.step(-jump);
          break;
        case "Home":
          pb.seek(0);
          break;
        case "End":
          pb.seek(total - 1);
          break;
        case "]":
          pb.setSpeed(SPEEDS[Math.min(SPEEDS.length - 1, speedIdx + 1)]);
          break;
        case "[":
          pb.setSpeed(SPEEDS[Math.max(0, speedIdx - 1)]);
          break;
        default:
          return;
      }
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pb, total]);
}
