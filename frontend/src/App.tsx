import { useEffect, useMemo, useState } from "react";
import { Controls } from "./components/Controls";
import { EventDetail } from "./components/EventDetail";
import { EventLog } from "./components/EventLog";
import { Explanation } from "./components/Explanation";
import { Inspector } from "./components/Inspector";
import { SourcePanel } from "./components/SourcePanel";
import { Timeline } from "./components/Timeline";
import { TraceInfo } from "./components/TraceInfo";
import { computeLayout } from "./models/layout";
import type { Replay } from "./models/replay";
import { buildStates } from "./models/states";
import { useKeyboard } from "./playback/useKeyboard";
import { usePlayback } from "./playback/usePlayback";
import { DataFlowView, type Selection } from "./views/DataFlowView";

type Tab = "event" | "source" | "inspect" | "log" | "info";
const TABS: [Tab, string][] = [
  ["event", "Event"], ["source", "Source"], ["inspect", "Inspect"],
  ["log", "Log"], ["info", "Trace"],
];

/** Same-origin only: a relative path, never a scheme or protocol-relative URL. */
function replayUrl(): string {
  const wanted = new URLSearchParams(location.search).get("replay");
  return wanted && /^[\w./-]+$/.test(wanted) && !wanted.startsWith("/")
    ? wanted : "api/replay";
}

export function App() {
  const [replay, setReplay] = useState<Replay | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetch(replayUrl())
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setReplay)
      .catch((e) => setError(String(e)));
  }, []);
  const [theme, setTheme] = useState<"dark" | "light">(
    () => (localStorage.getItem("concurim-theme") as "dark" | "light" | null) ??
      (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"),
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("concurim-theme", theme);
  }, [theme]);

  if (error) return <div className="splash error">Could not load the trace: {error}</div>;
  if (!replay) return <div className="splash">Loading trace…</div>;
  if (replay.events.length === 0) {
    return <div className="splash">This trace contains no events.</div>;
  }
  return <Viewer replay={replay}
    onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")} />;
}

function Viewer({ replay, onToggleTheme }: { replay: Replay; onToggleTheme: () => void }) {
  const states = useMemo(() => buildStates(replay), [replay]);
  const layout = useMemo(() => computeLayout(replay), [replay]);
  const indexById = useMemo(
    () => new Map(replay.events.map((e, i) => [e.event_id, i])), [replay]);
  const pb = usePlayback(replay.events);
  useKeyboard(pb, replay.events.length);
  const [selection, setSelection] = useState<Selection>(null);
  const [tab, setTab] = useState<Tab>("event");

  const event = replay.events[pb.index];
  const frame = replay.frames[pb.index];
  const select = (s: Selection) => {
    setSelection(s);
    if (s) setTab("inspect");
  };
  const meta = replay.metadata;
  return (
    <div className="app" style={{ "--dur": `${Math.max(120, 520 / pb.speed)}ms` } as React.CSSProperties}>
      <header className="top">
        <div className="brand"><b>Concurim</b><span>See how Python runs together</span></div>
        <div className="meta">
          {meta.program?.script ?? "trace"} · {replay.events.length} events ·{" "}
          {(replay.summary.duration_ns / 1e9).toFixed(2)}s
          {replay.warnings.length > 0 && (
            <button className="warn-chip" onClick={() => setTab("info")}
              data-testid="warnings">⚠ {replay.warnings.length}</button>
          )}
        </div>
      </header>
      <main className="stage">
        <section className="canvas" aria-label="Execution canvas">
          <DataFlowView replay={replay} layout={layout} world={states[pb.index]}
            frame={frame} event={event} selection={selection} onSelect={select} />
          <Legend />
        </section>
        <aside className="side">
          <Explanation frame={frame} event={event} />
          <nav className="tabs" role="tablist">
            {TABS.map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id}
                onClick={() => setTab(id)}>{label}</button>
            ))}
          </nav>
          <div className="tabpanel">
            {tab === "event" && <EventDetail replay={replay} event={event}
              indexById={indexById} onSeek={pb.seek} />}
            {tab === "source" && <SourcePanel replay={replay} event={event} />}
            {tab === "inspect" && <Inspector replay={replay}
              world={states[pb.index]} index={pb.index} selection={selection}
              onSeek={pb.seek} />}
            {tab === "log" && <EventLog replay={replay} index={pb.index} onSeek={pb.seek} />}
            {tab === "info" && <TraceInfo replay={replay} />}
          </div>
        </aside>
      </main>
      <Timeline replay={replay} layout={layout} index={pb.index} onSeek={pb.seek} />
      <Controls pb={pb} total={replay.events.length} onToggleTheme={onToggleTheme} />
    </div>
  );
}

function Legend() {
  const items: [string, string][] = [
    ["running", "var(--c-running)"], ["waiting", "var(--c-waiting)"],
    ["working", "var(--c-working)"], ["finished", "var(--c-finished)"],
    ["failed", "var(--c-failed)"],
  ];
  return (
    <div className="legend" aria-label="Legend">
      {items.map(([name, color]) => (
        <span key={name}><i style={{ background: color }} />{name}</span>
      ))}
      <span title="Dashed border: state inferred, not directly observed">
        <i className="dashed" />inferred
      </span>
    </div>
  );
}
