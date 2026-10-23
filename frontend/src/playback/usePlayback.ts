import { useCallback, useEffect, useRef, useState } from "react";
import type { TraceEvent } from "../models/replay";
import { clampIndex, delayBefore, type Pace } from "./stepping";

export interface Playback {
  index: number;
  playing: boolean;
  speed: number;
  pace: Pace;
  /** In real-time pace: shorten long idle gaps. */
  compress: boolean;
  /** Milliseconds visual transitions should take at this speed and pace. */
  motionMs: number;
  seek: (i: number) => void;
  step: (delta: number) => void;
  toggle: () => void;
  setSpeed: (s: number) => void;
  setPace: (p: Pace) => void;
  setCompress: (c: boolean) => void;
}

const MIN_MOTION_MS = 120;
const MAX_MOTION_MS = 520;

/**
 * Playback state. Position is always an event index, so a trace replays
 * identically every time; timers only decide *when* to advance.
 */
export function usePlayback(events: TraceEvent[]): Playback {
  const total = events.length;
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [pace, setPace] = useState<Pace>("explain");
  const [compress, setCompress] = useState(true);
  const indexRef = useRef(index);
  indexRef.current = index;

  const seek = useCallback(
    (i: number) => setIndex(clampIndex(i, total)),
    [total],
  );
  const step = useCallback(
    (d: number) => setIndex((i) => clampIndex(i + d, total)),
    [total],
  );
  const toggle = useCallback(() => {
    setPlaying((p) => {
      if (!p && indexRef.current >= total - 1) setIndex(0);
      return !p;
    });
  }, [total]);

  const nextDelay = index < total - 1
    ? delayBefore(events, index, speed, pace, compress)
    : 0;
  useEffect(() => {
    if (!playing) return;
    if (index >= total - 1) {
      setPlaying(false);
      return;
    }
    const id = window.setTimeout(() => setIndex(index + 1), nextDelay);
    return () => window.clearTimeout(id);
  }, [playing, index, total, nextDelay]);

  const base = Math.max(MIN_MOTION_MS, MAX_MOTION_MS / speed);
  const motionMs = playing && pace === "realtime"
    ? Math.max(MIN_MOTION_MS, Math.min(base, nextDelay))
    : base;
  return {
    index, playing, speed, pace, compress, motionMs,
    seek, step, toggle, setSpeed, setPace, setCompress,
  };
}
