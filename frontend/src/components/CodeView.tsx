import { useEffect, useMemo, useRef, useState } from "react";
import { buildMarkIndex, marksAt, shadesByLine, type Shade } from "../models/marks";
import { nameOf } from "../models/names";
import { actorOf, type Replay, type TraceEvent } from "../models/replay";
import type { WorldState } from "../models/states";
import { useSource } from "./useSource";

interface Props {
  replay: Replay;
  world: WorldState;
  index: number;
  event: TraceEvent;
}

const ALPHA: Record<Shade, number> = { line: 30, body: 18, context: 9 };

/** Line background: the worker's colour, or a blend when several share it. */
function tint(hit: { color: string; shade: Shade }[]): string {
  const mix = (h: { color: string; shade: Shade }) =>
    `color-mix(in srgb, ${h.color} ${ALPHA[h.shade]}%, transparent)`;
  if (hit.length === 1) return mix(hit[0]);
  return `linear-gradient(90deg, ${hit.map(mix).join(", ")})`;
}

/**
 * Read-only code beside the animation. Every active worker gets its current
 * line highlighted in the colour of the item it is working on, so the orb in
 * the graph and the line here match. When only the function is known (a task
 * that has just started), its whole body is shaded instead.
 */
export function CodeView({ replay, world, index, event }: Props) {
  const files = replay.source_paths;
  const marks = useMemo(() => buildMarkIndex(replay), [replay]);
  const now = marksAt(marks, world, index);
  const [pinned, setPinned] = useState<string | null>(null);
  const followed = (now.find((m) => m.actor === actorOf(event)) ?? now[0])?.file
    ?? event.source?.file;
  const file = pinned ?? (followed && files.includes(followed) ? followed : files[0]);
  const text = useSource(file ?? null, !!file);
  const here = now.filter((m) => m.file === file);
  const focus = here.find((m) => m.actor === actorOf(event)) ?? here[0];
  const focusRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    focusRef.current?.scrollIntoView({ block: "nearest" });
  }, [text, focus?.line, focus?.actor]);

  if (files.length === 0) {
    return (
      <div className="muted codeview-empty" data-testid="code-missing">
        <p>Source text is not part of this trace.</p>
        <p>Record with <code>--include-source</code> (or tick “Include source”
          on the home screen) to see the code here.</p>
        <p>Only files inside the script’s own folder are stored, never
          installed packages.</p>
      </div>
    );
  }
  const shades = shadesByLine(here);
  const lines = (text ?? "").split("\n");
  return (
    <div className="codeview" data-testid="codeview">
      <div className="codeview-head">
        {files.length > 1 ? (
          <select value={file} aria-label="Source file" data-testid="code-file"
            onChange={(e) => setPinned(e.target.value)}>
            {files.map((f) => <option key={f}>{f}</option>)}
          </select>
        ) : <span>{file}</span>}
        {pinned && (
          <button className="link" onClick={() => setPinned(null)}
            title="Follow the file of the current event again">follow</button>
        )}
      </div>
      <div className="code" data-testid="code">
        {lines.map((l, i) => {
          const hit = shades.get(i + 1);
          const bar = hit?.find((h) => h.shade !== "context");
          const chips = here.filter((m) => m.line === i + 1);
          return (
            <div key={i} className="line" data-hit={bar ? "" : undefined}
              data-shade={hit ? hit.map((h) => h.shade).join(" ") : undefined}
              ref={focus?.line === i + 1 ? focusRef : undefined}
              style={hit ? {
                background: tint(hit),
                boxShadow: bar ? `inset 3px 0 0 ${bar.color}` : undefined,
              } : undefined}>
              <span className="ln">{i + 1}</span>
              <span className="src">{l || " "}</span>
              {chips.length > 0 && (
                <span className="who-chips">
                  {chips.map((m) => (
                    <span key={m.actor} className="who-chip" data-testid="code-mark"
                      title={m.sampled ? "Sampled: approximate position" : undefined}
                      style={{ background: m.color }}>
                      {m.sampled ? "≈ " : ""}{nameOf(replay, m.actor)}
                    </span>
                  ))}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
