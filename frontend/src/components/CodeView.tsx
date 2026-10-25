import { useEffect, useMemo, useRef, useState } from "react";
import { buildMarkIndex, marksAt, type Mark } from "../models/marks";
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

/** Line background: the worker's colour, or a blend when several share it. */
function tint(hit: Mark[]): string {
  const mix = (c: string) => `color-mix(in srgb, ${c} 30%, transparent)`;
  if (hit.length === 1) return mix(hit[0].color);
  return `linear-gradient(90deg, ${hit.map((m) => mix(m.color)).join(", ")})`;
}

/**
 * Read-only code beside the animation. Every active worker gets its current
 * line highlighted in the colour of the item it is working on, so the orb in
 * the graph and the line here match.
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
      </div>
    );
  }
  const byLine = new Map<number, Mark[]>();
  for (const m of here) byLine.set(m.line, [...(byLine.get(m.line) ?? []), m]);
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
          const hit = byLine.get(i + 1);
          return (
            <div key={i} className="line" data-hit={hit ? "" : undefined}
              ref={hit && hit[0] === focus ? focusRef : undefined}
              style={hit ? {
                background: tint(hit),
                boxShadow: `inset 3px 0 0 ${hit[0].color}`,
              } : undefined}>
              <span className="ln">{i + 1}</span>
              <span className="src">{l || " "}</span>
              {hit && (
                <span className="who-chips">
                  {hit.map((m) => (
                    <span key={m.actor} className="who-chip" data-testid="code-mark"
                      style={{ background: m.color }}>
                      {nameOf(replay, m.actor)}
                    </span>
                  ))}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <p className="muted codeview-note">
        Each worker is shown at its last recorded location. Pool tasks sit on
        their function’s first line; blocked calls and awaits on the exact line.
      </p>
    </div>
  );
}
