import { SPEEDS } from "../playback/stepping";
import type { Playback } from "../playback/usePlayback";

interface Props {
  pb: Playback;
  total: number;
  onToggleTheme: () => void;
}

/** Transport bar: seek ends, step, play/pause, speed, scrubber. */
export function Controls({ pb, total, onToggleTheme }: Props) {
  const last = total - 1;
  return (
    <div className="controls" role="toolbar" aria-label="Playback">
      <button onClick={() => pb.seek(0)} title="Beginning (Home)"
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
      <label className="speed">
        speed
        <select value={pb.speed}
          onChange={(e) => pb.setSpeed(Number(e.target.value))}>
          {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
        </select>
      </label>
      <button onClick={onToggleTheme} title="Toggle theme" aria-label="Toggle theme">◐</button>
    </div>
  );
}
