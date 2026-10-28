import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CodeView } from "./components/CodeView";
import { RepoLink } from "./components/RepoLink";
import { Controls } from "./components/Controls";
import type { ExportCaps } from "./api/types";
import { EventDetail } from "./components/EventDetail";
import { EventLog } from "./components/EventLog";
import { Explanation } from "./components/Explanation";
import { Inspector } from "./components/Inspector";
import { Lineage } from "./components/Lineage";
import { readCapture, useCaptureBridge } from "./capture";
import { StuckBanner } from "./components/StuckBanner";
import { Timeline } from "./components/Timeline";
import { TraceInfo } from "./components/TraceInfo";
import { ExportDialog } from "./export/ExportDialog";
import { computeLayout } from "./models/layout";
import type { Replay } from "./models/replay";
import type { Selection } from "./models/selection";
import { buildStates } from "./models/states";
import { nextBlocking, nextForSelection } from "./playback/navigation";
import { useKeyboard, type KeyActions } from "./playback/useKeyboard";
import { usePlayback } from "./playback/usePlayback";
import { FlowView } from "./views/FlowView";
import { ResourceView } from "./views/ResourceView";

type Tab = "event" | "inspect" | "lineage" | "log" | "info";
type Mode = "animation" | "timeline" | "code" | "resources";
const MODES: [Mode, string][] = [
  ["animation", "Animation"], ["code", "Code"], ["resources", "Resources"],
  ["timeline", "Timeline"],
];
const TABS: [Tab, string][] = [
  ["event", "Event"], ["inspect", "Inspect"], ["lineage", "Lineage"],
  ["log", "Log"], ["info", "Trace"],
];
const MODE_KEY = "concurim-mode";

function initialMode(): Mode {
  const saved = localStorage.getItem(MODE_KEY);
  return saved === "timeline" || saved === "code" || saved === "resources"
    ? saved : "animation";
}

interface Props {
  replay: Replay;
  label: string;
  theme: "dark" | "light";
  onToggleTheme: () => void;
  onHome: () => void;
  /** What the server can export; null when there is no server (dev). */
  exportCaps: ExportCaps | null;
}

/**
 * One recording, two views over the same replay: Animation (understanding:
 * data flowing between workers and queues) and Timeline (dense, precise).
 * Both share one playback position, so an event picked in one is the event
 * shown in the other.
 */
export function Viewer({
  replay, label, theme, onToggleTheme, onHome, exportCaps,
}: Props) {
  const states = useMemo(() => buildStates(replay), [replay]);
  const layout = useMemo(() => computeLayout(replay), [replay]);
  const indexById = useMemo(
    () => new Map(replay.events.map((e, i) => [e.event_id, i])), [replay]);
  const pb = usePlayback(replay.events);
  const [selection, setSelection] = useState<Selection>(null);
  const [tab, setTab] = useState<Tab>("event");
  const capture = useMemo(() => readCapture(location.search), []);
  const [mode, setModeState] = useState<Mode>(
    () => capture?.view ?? initialMode());
  const [fitTick, setFitTick] = useState(0);
  const [fullscreen, setFs] = useState(false);
  const [exporting, setExporting] = useState(false);
  const appRef = useRef<HTMLDivElement | null>(null);

  // Real browser fullscreen when allowed; otherwise the same layout in-page.
  const setFullscreen = useCallback((on: boolean) => {
    setFs(on);
    if (on) appRef.current?.requestFullscreen?.().catch(() => undefined);
    else if (document.fullscreenElement) document.exitFullscreen().catch(() => undefined);
  }, []);
  useEffect(() => {
    const onChange = () => { if (!document.fullscreenElement) setFs(false); };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  // The canvas changes size: fit the graph again once it has settled.
  useEffect(() => {
    const id = window.setTimeout(() => setFitTick((t) => t + 1), 120);
    return () => window.clearTimeout(id);
  }, [fullscreen, mode]);

  const setMode = (m: Mode) => {
    setModeState(m);
    localStorage.setItem(MODE_KEY, m);
  };
  useCaptureBridge(!!capture, replay.events.length, pb.seek);
  // Videos glide for a fixed time on a clock the exporter winds by hand.
  const motionMs = capture ? capture.motionMs : pb.motionMs;
  const jump = (to: number | null) => to !== null && pb.seek(to);
  const actions: KeyActions = {
    blocking: (dir) => jump(nextBlocking(replay.events, pb.index, dir)),
    selection: (dir) => jump(nextForSelection(replay.events, pb.index, selection, dir)),
    fit: () => setFitTick((t) => t + 1),
    fullscreen: () => setFullscreen(!fullscreen),
    escape: () => { if (fullscreen) setFullscreen(false); },
  };
  useKeyboard(pb, replay.events.length, actions);

  const event = replay.events[pb.index];
  const frame = replay.frames[pb.index];
  const select = (s: Selection) => {
    setSelection(s);
    if (s) setTab("inspect");
  };
  const meta = replay.metadata;
  return (
    <div className="app" data-mode={mode} data-fullscreen={fullscreen || undefined}
      ref={appRef} style={{ "--dur": `${motionMs}ms` } as React.CSSProperties}
      data-capture={capture ? "" : undefined}
      data-index={capture ? pb.index : undefined}
      data-hide-explanation={capture && !capture.overlays.has("explanation")
        ? "" : undefined}
      data-hide-timeline={capture && !capture.overlays.has("timeline")
        ? "" : undefined}>
      <header className="top">
        <div className="brand">
          <button className="link brand-home" onClick={onHome} data-testid="home"
            title="Back to the home screen">
            <b>Concurim</b>
          </button>
          <span>See how Python runs together</span>
        </div>
        <div className="mode" role="radiogroup" aria-label="View mode">
          {MODES.map(([m, name]) => (
            <button key={m} role="radio" aria-checked={mode === m}
              data-testid={`mode-${m}`} onClick={() => setMode(m)}>
              {name}
            </button>
          ))}
        </div>
        <div className="meta">
          <RepoLink />
          {exportCaps && (
            <button className="export-btn" data-testid="open-export"
              onClick={() => setExporting(true)}
              title="Render this recording as a video, GIF or images">
              Export…
            </button>
          )}
          {label || meta.program?.script || "trace"} · {replay.events.length} events ·{" "}
          {(replay.summary.duration_ns / 1e9).toFixed(2)}s
          {replay.warnings.length > 0 && (
            <button className="warn-chip" onClick={() => setTab("info")}
              data-testid="warnings">⚠ {replay.warnings.length}</button>
          )}
        </div>
      </header>
      <StuckBanner replay={replay} onShow={pb.seek} />
      <main className="stage">
        <section className="canvas" aria-label="Execution canvas">
          {mode === "resources" ? (
            <ResourceView replay={replay} world={states[pb.index]}
              selection={selection} onSelect={select} />
          ) : mode !== "timeline" ? (
            <>
              <FlowView replay={replay} layout={layout} world={states[pb.index]}
                frame={frame} event={event} selection={selection}
                onSelect={select} motionMs={motionMs} theme={theme}
                fitTick={fitTick} />
              <Legend />
              {fullscreen && mode === "animation" && (
                <div className="caption">
                  <Explanation frame={frame} event={event} />
                </div>
              )}
              {fullscreen && (
                <button className="exit-fs" data-testid="exit-fullscreen"
                  onClick={() => setFullscreen(false)}>⤡ Exit fullscreen</button>
              )}
            </>
          ) : (
            <Timeline variant="full" replay={replay} layout={layout}
              index={pb.index} onSeek={pb.seek}
              onOpenInAnimation={() => setMode("animation")} />
          )}
        </section>
        <aside className="side">
          <Explanation frame={frame} event={event} />
          {mode === "code" ? (
            <CodeView replay={replay} world={states[pb.index]} index={pb.index}
              event={event} />
          ) : <>
          <nav className="tabs" role="tablist">
            {TABS.map(([id, name]) => (
              <button key={id} role="tab" aria-selected={tab === id}
                onClick={() => setTab(id)}>{name}</button>
            ))}
          </nav>
          <div className="tabpanel">
            {tab === "event" && <EventDetail replay={replay} event={event}
              indexById={indexById} onSeek={pb.seek}
              onOpenCode={() => setMode("code")} />}
            {tab === "inspect" && <Inspector replay={replay}
              world={states[pb.index]} index={pb.index} selection={selection}
              onSeek={pb.seek} />}
            {tab === "lineage" && <Lineage replay={replay}
              world={states[pb.index]} index={pb.index} selection={selection}
              currentObject={event?.object_id ?? null}
              onFocus={(id) => setSelection({ kind: "object", id })}
              onSeek={pb.seek} />}
            {tab === "log" && <EventLog replay={replay} index={pb.index} onSeek={pb.seek} />}
            {tab === "info" && <TraceInfo replay={replay} />}
          </div>
          </>}
        </aside>
      </main>
      {mode !== "timeline" && (
        <Timeline replay={replay} layout={layout} index={pb.index} onSeek={pb.seek} />
      )}
      {exporting && exportCaps && (
        <ExportDialog caps={exportCaps} view={mode} index={pb.index}
          total={replay.events.length} onClose={() => setExporting(false)} />
      )}
      {capture?.watermark && (
        <div className="watermark" data-testid="watermark">
          <img src="logo.png" alt="" width={22} height={22} />
          <span>Concurim</span>
        </div>
      )}
      {capture ? (
        capture.footer && <footer className="capture-footer"
          data-testid="capture-footer">{capture.footer}</footer>
      ) : (
        <Controls pb={pb} total={replay.events.length}
          onToggleTheme={onToggleTheme}
          onJumpBlocking={actions.blocking} onJumpSelection={actions.selection}
          hasSelection={!!selection} fullscreen={fullscreen}
          onToggleFullscreen={() => setFullscreen(!fullscreen)} />
      )}
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
