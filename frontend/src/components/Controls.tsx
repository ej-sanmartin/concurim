import { SPEEDS } from "../playback/stepping";
import type { Playback } from "../playback/usePlayback";

interface Props {
  pb: Playback;
  total: number;
  onToggleTheme: () => void;
  onJumpBlocking: (dir: 1 | -1) => void;
  onJumpSelection: (dir: 1 | -1) => void;
  /** Whether something is selected (enables jumping between its events). */
  hasSelection: boolean;
  fullscreen: boolean;
  onToggleFullscreen: () => void;
}

/** Transport bar: seek ends, step, play/pause, jumps, pace, speed, scrubber. */
export function Controls({
  pb, total, onToggleTheme, onJumpBlocking, onJumpSelection, hasSelection,
  fullscreen, onToggleFullscreen,
}: Props) {
  const last = total - 1;
  return (
    <div className="controls" role="toolbar" aria-label="Playback">
      <button onClick={() => pb.seek(0)} title="Reset to start (Home)"
        aria-label="Beginning" disabled={pb.index === 0}>⏮</button>
      <button onClick={() => pb.step(-1)} title="Previous event (←)"
        data-testid="prev" aria-label="Previous event"
        disabled={pb.index === 0}>◀</button>
      <button className="primary" onClick={pb.toggle} data-testid="play"
        title="Play / pause (Space)"
        aria-label={pb.playing ? "Pause" : "Play"}>
        {pb.playing ? "⏸" : "▶"}
      </button>
      <button onClick={() => pb.step(1)} title="Next event (→)"
        data-testid="next" aria-label="Next event"
        disabled={pb.index === last}>▶</button>
      <button onClick={() => pb.seek(last)} title="End (End)"
        aria-label="End" disabled={pb.index === last}>⏭</button>
      <button onClick={() => onJumpBlocking(1)} data-testid="next-blocking"
        title="Jump to the next blocking event (b; Shift+B for previous)">
        ⏳ next block
      </button>
      <button onClick={() => onJumpSelection(1)} data-testid="next-selected"
        disabled={!hasSelection}
        title="Jump to the next event of the selected thread, queue or item (n)">
        ⇥ next for selection
      </button>
      <input className="scrubber" type="range" min={0} max={last}
        value={pb.index} aria-label="Seek to event"
        onChange={(e) => pb.seek(Number(e.target.value))} />
      <label className="goto">
        event
        <input type="number" min={1} max={total} value={pb.index + 1}
          data-testid="goto"
          onChange={(e) => pb.seek(Number(e.target.value) - 1)} />
        <span data-testid="position">/ {total}</span>
      </label>
      <label className="pace"
        title="Explanatory: one steady beat per event. Real time: the recorded gaps.">
        pace
        <select value={pb.pace} data-testid="pace"
          onChange={(e) => pb.setPace(e.target.value as "explain" | "realtime")}>
          <option value="explain">Explanatory</option>
          <option value="realtime">Real time</option>
        </select>
      </label>
      {pb.pace === "realtime" && (
        <label title="Shorten long idle gaps so a sleep does not stall the replay">
          <input type="checkbox" checked={pb.compress} data-testid="compress"
            onChange={(e) => pb.setCompress(e.target.checked)} />
          compress idle
        </label>
      )}
      <label className="speed">
        speed
        <select value={pb.speed} data-testid="speed"
          onChange={(e) => pb.setSpeed(Number(e.target.value))}>
          {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
        </select>
      </label>
      <button onClick={onToggleTheme} title="Toggle theme" aria-label="Toggle theme">◐</button>
      <button onClick={onToggleFullscreen} data-testid="fullscreen"
        aria-pressed={fullscreen} className="fs-toggle"
        title={fullscreen ? "Exit fullscreen (z or Esc)" : "Fullscreen animation (z)"}
        aria-label={fullscreen ? "Exit fullscreen" : "Fullscreen"}>
        {fullscreen ? "⤡" : "⤢"}
      </button>
    </div>
  );
}
