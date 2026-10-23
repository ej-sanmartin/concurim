import { useEffect, useRef, useState } from "react";
import type { Replay, TraceEvent } from "../models/replay";

const cache = new Map<string, string>();

/** Source file for the current event with its line highlighted. */
export function SourcePanel({ replay, event }: { replay: Replay; event: TraceEvent }) {
  const src = event.source;
  const embedded = !!src && replay.source_paths.includes(src.file);
  const [text, setText] = useState<string | null>(null);
  const lineRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!src || !embedded) return setText(null);
    const hit = cache.get(src.file);
    if (hit !== undefined) return setText(hit);
    let alive = true;
    fetch(`api/source?path=${encodeURIComponent(src.file)}`)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((t) => {
        cache.set(src.file, t);
        if (alive) setText(t);
      })
      .catch(() => alive && setText(null));
    return () => { alive = false; };
  }, [src?.file, embedded]);

  useEffect(() => {
    lineRef.current?.scrollIntoView({ block: "center", behavior: "auto" });
  }, [text, src?.line]);

  if (!src) {
    return <p className="muted">This event has no recorded source location.</p>;
  }
  if (!embedded || text === null) {
    return (
      <div className="muted" data-testid="source-missing">
        <p><code>{src.file}:{src.line}</code> in <code>{src.function}</code></p>
        <p>Source text is not part of this trace. Record with
          {" "}<code>--include-source</code> to inspect it here.</p>
      </div>
    );
  }
  const lines = text.split("\n");
  return (
    <div className="source" data-testid="source">
      <div className="source-head">{src.file} · line {src.line} · {src.function}</div>
      <div className="code">
        {lines.map((l, i) => {
          const hit = i + 1 === src.line;
          return (
            <div key={i} className="line" data-hit={hit || undefined}
              ref={hit ? lineRef : undefined}>
              <span className="ln">{i + 1}</span>
              <span className="src">{l || " "}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
