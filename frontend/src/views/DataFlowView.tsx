import type { Layout, Point } from "../models/layout";
import { NODE_H, NODE_W, SLOT_SIZE, slotPoint } from "../models/layout";
import type { Frame, QueueState, Replay, ThreadState, TraceEvent } from "../models/replay";
import type { WorldState } from "../models/states";
import { STATUS_COLOR, objectColor, objectLabel } from "../animations/palette";

export type Selection =
  | { kind: "thread" | "queue" | "object"; id: string }
  | null;

interface Props {
  replay: Replay;
  layout: Layout;
  world: WorldState;
  frame: Frame;
  event: TraceEvent;
  selection: Selection;
  onSelect: (s: Selection) => void;
}

/** Spatial view: threads and queues, with items gliding between them. */
export function DataFlowView(p: Props) {
  const { layout, world, frame, event, selection } = p;
  const handIndex = handSlots(world);
  return (
    <svg
      className="flow"
      data-testid="flow"
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      role="img"
      aria-label="Threads and queues"
      onClick={() => p.onSelect(null)}
    >
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" className="arrowhead" />
        </marker>
      </defs>
      {layout.edges.map((e) => (
        <Edge key={`${e.thread}-${e.queue}-${e.dir}`} layout={layout}
          edge={e} frame={frame} />
      ))}
      {Object.entries(layout.queues).map(([id, pos]) => (
        <QueueBox key={id} pos={pos} state={world.queues[id]}
          name={p.replay.entities.queues[id].name}
          maxsize={p.replay.entities.queues[id].maxsize}
          active={event.resource_id === id}
          selected={selection?.kind === "queue" && selection.id === id}
          onSelect={() => p.onSelect({ kind: "queue", id })} />
      ))}
      {layout.threadOrder.map((id) => (
        <ThreadNode key={id} pos={layout.threads[id]}
          name={p.replay.entities.threads[id].name}
          state={world.threads[id]} queues={p.replay.entities.queues}
          active={event.thread_id === id}
          selected={selection?.kind === "thread" && selection.id === id}
          onSelect={() => p.onSelect({ kind: "thread", id })} />
      ))}
      {Object.values(world.objects).map((o) => {
        const pt = objectPoint(o.id, world, layout, handIndex);
        if (!pt) return null;
        const hidden = o.phase === "released" || o.phase === "discarded";
        const holder = o.at ? world.threads[o.at] : undefined;
        const blocked = o.phase === "putting" && holder?.status === "waiting";
        return (
          <g key={o.id} className="token" data-testid={`token-${o.id}`}
            data-phase={o.phase} data-hidden={hidden || undefined}
            style={{ transform: `translate(${pt.x}px, ${pt.y}px)` }}
            onClick={(e) => {
              e.stopPropagation();
              p.onSelect({ kind: "object", id: o.id });
            }}>
            <g className="pop">
              <circle r={SLOT_SIZE / 2 - 8} fill={objectColor(o.id)}
                className={blocked ? "blocked-token" : undefined}
                data-selected={
                  (selection?.kind === "object" && selection.id === o.id) ||
                  undefined
                } />
              <text className="token-label" textAnchor="middle" dy="0.35em">
                {objectLabel(o.id)}
              </text>
              <title>
                {o.id}
                {o.preview ? ` (${o.preview})` : ""} — {o.phase}
              </title>
            </g>
          </g>
        );
      })}
    </svg>
  );
}

function Edge(p: { layout: Layout; edge: Layout["edges"][number]; frame: Frame }) {
  const t = p.layout.threads[p.edge.thread];
  const q = p.layout.queues[p.edge.queue];
  const put = p.edge.dir === "put";
  const a: Point = put
    ? { x: t.x + NODE_W / 2, y: t.y }
    : { x: q.x + q.w / 2, y: q.y };
  const b: Point = put
    ? { x: q.x - q.w / 2, y: q.y }
    : { x: t.x - NODE_W / 2, y: t.y };
  const mx = (a.x + b.x) / 2;
  const m = p.frame.motion;
  const active = !!m && (put
    ? m.from === p.edge.thread && m.to === p.edge.queue
    : m.from === p.edge.queue && m.to === p.edge.thread);
  return (
    <path className="edge" data-active={active || undefined}
      d={`M${a.x},${a.y} C${mx},${a.y} ${mx},${b.y} ${b.x},${b.y}`}
      markerEnd="url(#arrow)" />
  );
}

function QueueBox(p: {
  pos: Layout["queues"][string];
  state?: QueueState;
  name: string;
  maxsize: number;
  active: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  const { pos, state } = p;
  const size = state?.size ?? 0;
  const full = p.maxsize > 0 && size >= p.maxsize;
  const overflow = Math.max(0, size - pos.slots);
  const cap = p.maxsize > 0 ? String(p.maxsize) : "∞";
  return (
    <g data-testid="queue" onClick={(e) => { e.stopPropagation(); p.onSelect(); }}
      className="node queue" data-active={p.active || undefined}
      data-selected={p.selected || undefined}>
      <rect x={pos.x - pos.w / 2} y={pos.y - 34} width={pos.w} height={68}
        rx={14} className="queue-box" data-full={full || undefined}
        data-shutdown={state?.shutdown ?? undefined} />
      {Array.from({ length: pos.slots }, (_, i) => {
        const s = slotPoint(pos, i);
        return <rect key={i} x={s.x - SLOT_SIZE / 2 + 5} y={s.y - 18}
          width={SLOT_SIZE - 10} height={36} rx={9} className="slot" />;
      })}
      <text x={pos.x} y={pos.y - 46} textAnchor="middle" className="node-title">
        {p.name}
      </text>
      <text x={pos.x} y={pos.y + 56} textAnchor="middle" className="node-sub"
        data-testid="queue-stats">
        {`${size} / ${cap} queued · ${state?.unfinished ?? 0} unfinished`}
      </text>
      {overflow > 0 && (
        <text x={pos.x - pos.w / 2 + 12} y={pos.y + 4} className="node-sub">
          +{overflow}
        </text>
      )}
      <text x={pos.x + pos.w / 2 - 6} y={pos.y - 40} textAnchor="end"
        className="tiny">
        front →
      </text>
      {state?.shutdown && (
        <text x={pos.x} y={pos.y + 74} textAnchor="middle" className="badge-warn">
          {state.shutdown === "immediate" ? "shut down (immediate)" : "shut down"}
        </text>
      )}
    </g>
  );
}

function waitText(s: ThreadState, queues: Replay["entities"]["queues"]): string {
  if (s.status === "waiting" && s.waiting_on) {
    const q = queues[s.waiting_on.queue]?.name ?? s.waiting_on.queue;
    const verb = { put: "put on", get: "get from", join: "join" }[s.waiting_on.op];
    return `waiting to ${verb ?? s.waiting_on.op} ${q}`;
  }
  if (s.status === "working") return `working: ${s.work ?? ""}`;
  if (s.status === "running") return "running (not blocked)";
  return s.status;
}

function ThreadNode(p: {
  pos: Layout["threads"][string];
  name: string;
  state?: ThreadState;
  queues: Replay["entities"]["queues"];
  active: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  const { pos, state } = p;
  const color = state ? STATUS_COLOR[state.status] : "var(--c-idle)";
  return (
    <g data-testid="thread" data-thread={p.name} data-status={state?.status ?? "unseen"}
      className="node thread" data-active={p.active || undefined}
      data-selected={p.selected || undefined} opacity={state ? 1 : 0.35}
      onClick={(e) => { e.stopPropagation(); p.onSelect(); }}>
      <rect x={pos.x - NODE_W / 2} y={pos.y - NODE_H / 2} width={NODE_W}
        height={NODE_H} rx={14} className="thread-box" stroke={color}
        strokeDasharray={state?.basis === "inferred" ? "5 4" : undefined} />
      <text x={pos.x - NODE_W / 2 + 16} y={pos.y - 17} className="tiny">
        {pos.role}
      </text>
      <circle cx={pos.x - NODE_W / 2 + 21} cy={pos.y + 0} r={5} fill={color}
        className={state?.status === "waiting" ? "pulse" : undefined} />
      <text x={pos.x - NODE_W / 2 + 34} y={pos.y + 5} className="node-title">
        {p.name}
      </text>
      <text x={pos.x - NODE_W / 2 + 16} y={pos.y + 25} className="node-sub">
        {state ? waitText(state, p.queues) : "not seen yet"}
      </text>
    </g>
  );
}

/** Index of each hand-held object among the objects at the same thread. */
function handSlots(world: WorldState): Map<string, { i: number; n: number }> {
  const byThread = new Map<string, string[]>();
  for (const o of Object.values(world.objects)) {
    if ((o.phase === "held" || o.phase === "putting") && o.at) {
      byThread.set(o.at, [...(byThread.get(o.at) ?? []), o.id]);
    }
  }
  const out = new Map<string, { i: number; n: number }>();
  for (const ids of byThread.values()) {
    ids.sort();
    ids.forEach((id, i) => out.set(id, { i, n: ids.length }));
  }
  return out;
}

function objectPoint(
  id: string,
  world: WorldState,
  layout: Layout,
  hands: Map<string, { i: number; n: number }>,
): Point | null {
  const o = world.objects[id];
  if (!o.at || o.phase === "new") return null;
  const queue = layout.queues[o.at];
  if (queue) {
    if (o.phase === "queued") {
      const idx = world.queues[o.at]?.items.indexOf(id) ?? -1;
      return idx < 0 ? null : slotPoint(queue, idx);
    }
    return { x: queue.x, y: queue.y + 90 }; // discarded
  }
  const t = layout.threads[o.at];
  if (!t) return null;
  const h = hands.get(id) ?? { i: 0, n: 1 };
  return { x: t.x + (h.i - (h.n - 1) / 2) * 38, y: t.y - NODE_H / 2 - 26 };
}
