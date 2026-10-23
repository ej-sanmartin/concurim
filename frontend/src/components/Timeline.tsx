import { useEffect, useRef, useState } from "react";
import type { Layout } from "../models/layout";
import type { Replay } from "../models/replay";
import { indexAtTime } from "../models/states";

const LANE = 28;
const OCC = 56;
const BASE_W = 1200;
const ZOOMS = [1, 2, 4, 8, 16];
const MAX_TICKS = 4000;

interface Props {
  replay: Replay;
  layout: Layout;
  index: number;
  onSeek: (i: number) => void;
}

/** Lanes per thread, wait/work spans, queue occupancy and the playhead. */
export function Timeline({ replay, layout, index, onSeek }: Props) {
  const [zoom, setZoom] = useState(1);
  const [mode, setMode] = useState<"event" | "time">("event");
  const scroller = useRef<HTMLDivElement | null>(null);
  const events = replay.events;
  const n = events.length;
  const W = BASE_W * zoom;
  const total = Math.max(1, events[n - 1]?.timestamp_ns ?? 1);
  const xOf = (i: number) =>
    mode === "time"
      ? (events[i].timestamp_ns / total) * W
      : (n > 1 ? i / (n - 1) : 0) * W;
  const lanes = layout.threadOrder;
  const queues = Object.keys(replay.entities.queues);
  const H = lanes.length * LANE + queues.length * OCC + 8;
  const laneY = (t: string) => lanes.indexOf(t) * LANE;

  const seekFromPointer = (e: React.PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientX - box.left) / box.width));
    onSeek(mode === "time" ? indexAtTime(replay, frac * total) : Math.round(frac * (n - 1)));
  };

  useEffect(() => {
    const el = scroller.current;
    if (!el || n === 0) return;
    const x = xOf(index) * (el.scrollWidth / W);
    if (x < el.scrollLeft + 40 || x > el.scrollLeft + el.clientWidth - 40) {
      el.scrollLeft = x - el.clientWidth / 2;
    }
  });

  return (
    <div className="timeline" data-testid="timeline">
      <div className="tl-tools">
        <span>Timeline</span>
        <button onClick={() => setMode(mode === "event" ? "time" : "event")}
          title="Switch the horizontal axis">
          axis: {mode === "event" ? "event order" : "elapsed time"}
        </button>
        <button disabled={zoom === ZOOMS[0]} aria-label="Zoom out"
          onClick={() => setZoom(ZOOMS[Math.max(0, ZOOMS.indexOf(zoom) - 1)])}>−</button>
        <span>{zoom}×</span>
        <button disabled={zoom === ZOOMS[ZOOMS.length - 1]} aria-label="Zoom in"
          onClick={() => setZoom(ZOOMS[Math.min(ZOOMS.length - 1, ZOOMS.indexOf(zoom) + 1)])}>+</button>
      </div>
      <div className="tl-body">
        <div className="tl-labels" style={{ paddingTop: 0 }}>
          {lanes.map((t) => (
            <div key={t} style={{ height: LANE }}>{replay.entities.threads[t].name}</div>
          ))}
          {queues.map((q) => (
            <div key={q} style={{ height: OCC }}>{replay.entities.queues[q].name}</div>
          ))}
        </div>
        <div className="tl-scroll" ref={scroller}>
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
            style={{ width: `${zoom * 100}%`, height: H }} onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            seekFromPointer(e);
          }} onPointerMove={(e) => {
            if (e.buttons === 1) seekFromPointer(e);
          }}>
            {lanes.map((t, li) => (
              <rect key={t} x={0} y={li * LANE} width={W} height={LANE}
                className={li % 2 ? "lane odd" : "lane"} />
            ))}
            {lanes.map((t) => {
              const ent = replay.entities.threads[t];
              return (
                <line key={t} x1={xOf(ent.first)} x2={xOf(ent.last)}
                  y1={laneY(t) + LANE / 2} y2={laneY(t) + LANE / 2}
                  className="life" />
              );
            })}
            {replay.spans.map((s) => {
              if (!s.thread || !lanes.includes(s.thread)) return null;
              const x1 = xOf(s.start);
              return (
                <rect key={s.operation} data-testid="span"
                  x={x1} y={laneY(s.thread) + 6}
                  width={Math.max(2, xOf(s.end) - x1)} height={LANE - 12}
                  rx={3} className={`span span-${s.kind} out-${s.outcome}`}>
                  <title>{`${s.kind.replace("_", " ")} (${s.outcome})${s.name ? `: ${s.name}` : ""}`}</title>
                </rect>
              );
            })}
            {n <= MAX_TICKS && events.map((e, i) => {
              if (!e.thread_id || !lanes.includes(e.thread_id)) return null;
              const tone = replay.frames[i].explanation.tone;
              return (
                <line key={i} x1={xOf(i)} x2={xOf(i)}
                  y1={laneY(e.thread_id) + 3} y2={laneY(e.thread_id) + LANE - 3}
                  className={`tick tone-${tone}`} />
              );
            })}
            {queues.map((q, qi) => (
              <Occupancy key={q} replay={replay} queue={q} xOf={xOf}
                y={lanes.length * LANE + qi * OCC} W={W} n={n} />
            ))}
            <line x1={xOf(index)} x2={xOf(index)} y1={0} y2={H}
              className="playhead" data-testid="playhead" />
          </svg>
        </div>
      </div>
    </div>
  );
}

function Occupancy(p: {
  replay: Replay; queue: string; xOf: (i: number) => number;
  y: number; W: number; n: number;
}) {
  const pts = p.replay.occupancy[p.queue] ?? [];
  const cap = p.replay.entities.queues[p.queue].maxsize;
  const peak = Math.max(1, cap, ...pts.map((o) => Math.max(o[1], o[2])));
  const h = OCC - 14;
  const yOf = (v: number) => p.y + 7 + h - (v / peak) * h;
  const path = (col: 1 | 2) => {
    let d = "";
    let last = 0;
    for (const o of pts) {
      const x = p.xOf(o[0]);
      d += `${d ? "L" : "M"}${x},${yOf(last)} L${x},${yOf(o[col])} `;
      last = o[col];
    }
    return d + `L${p.xOf(Math.max(0, p.n - 1))},${yOf(last)}`;
  };
  return (
    <g className="occ">
      <rect x={0} y={p.y} width={p.W} height={OCC} className="lane" />
      {cap > 0 && (
        <line x1={0} x2={p.W} y1={yOf(cap)} y2={yOf(cap)} className="capline" />
      )}
      {pts.length > 0 && <path d={path(2)} className="unfinished-line" />}
      {pts.length > 0 && <path d={path(1)} className="occ-line" />}
    </g>
  );
}
