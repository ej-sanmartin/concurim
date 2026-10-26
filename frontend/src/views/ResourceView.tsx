import { STATUS_COLOR } from "../animations/palette";
import { nameOf } from "../models/names";
import type { Replay } from "../models/replay";
import { buildResourceGraph } from "../models/resources";
import type { Selection } from "../models/selection";
import type { WorldState } from "../models/states";
import { KIND_LABEL, summarize } from "./SyncNode";

interface Props {
  replay: Replay;
  world: WorldState;
  selection: Selection;
  onSelect: (s: Selection) => void;
}

const W = 720;
const BOX_W = 230;
const BOX_H = 44;
const GAP = 16;
const TOP = 20;

/** Vertical centre of row `i`. */
const rowY = (i: number) => TOP + i * (BOX_H + GAP) + BOX_H / 2;

/** One-line state for a queue, executor or sync resource. */
function describe(replay: Replay, world: WorldState, id: string): [string, string] {
  const q = world.queues[id];
  if (q) {
    const cap = q.maxsize > 0 ? q.maxsize : "∞";
    return [q.kind, `${q.size} / ${cap} queued`];
  }
  const s = world.syncs[id];
  const info = replay.entities.syncs[id];
  return [KIND_LABEL[s.kind], summarize(s.kind, info, s, replay).text];
}

/**
 * Curve between an actor box and a resource box. A hold points from the
 * resource to the actor; every other relation points from the actor.
 */
function curve(ai: number, ri: number, towardActor: boolean): string {
  const left = BOX_W + 20;
  const right = W - BOX_W - 20;
  const mid = (left + right) / 2;
  const [ya, yr] = [rowY(ai), rowY(ri)];
  return towardActor
    ? `M ${right} ${yr} C ${mid} ${yr}, ${mid} ${ya}, ${left} ${ya}`
    : `M ${left} ${ya} C ${mid} ${ya}, ${mid} ${yr}, ${right} ${yr}`;
}

/**
 * Synchronization graph: who holds and who waits for each resource right
 * now. It is rebuilt from the replayed state at every event, so stepping
 * shows holds and waits appear and disappear. A circular wait between locks
 * is highlighted; it is derived from observed holds and waits only.
 */
export function ResourceView({ replay, world, selection, onSelect }: Props) {
  const g = buildResourceGraph(world);
  const rows = Math.max(g.actors.length, g.resources.length, 1);
  const height = TOP * 2 + rows * (BOX_H + GAP);
  const name = (id: string) => nameOf(replay, id);
  const pick = (kind: "thread" | "queue" | "sync", id: string) =>
    onSelect({ kind, id });
  const isSel = (id: string) => selection?.id === id || undefined;
  const actorAt = new Map(g.actors.map((a, i) => [a, i]));
  const resourceAt = new Map(g.resources.map((r, i) => [r, i]));
  return (
    <div className="resource-view" data-testid="resource-view">
      {g.cycle.length > 0 && (
        <p className="cycle-note" role="alert" data-testid="cycle-note">
          Circular wait: {g.cycle.map(name).join(" ↔ ")}. Each one waits for a
          lock another one in the circle holds, so none of them can continue
          until a timeout or an error breaks the circle.
        </p>
      )}
      <svg viewBox={`0 0 ${W} ${height}`} width="100%" role="img"
        aria-label="Synchronization graph">
        <defs>
          {["holds", "waits", "cycle"].map((k) => (
            <marker key={k} id={`arrow-${k}`} viewBox="0 0 8 8" refX="7" refY="4"
              markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10"
              orient="auto">
              <path d="M 0 0 L 8 4 L 0 8 z" className={`arrow arrow-${k}`} />
            </marker>
          ))}
        </defs>
        {g.edges.map((e) => {
          const a = actorAt.get(e.actor);
          const r = resourceAt.get(e.resource);
          if (a === undefined || r === undefined) return null;
          const kind = e.cycle ? "cycle" : e.kind;
          // Holds are labelled near the resource, the rest near the actor, so
          // two edges between the same boxes do not share a label spot.
          const hold = e.kind === "holds";
          const y = rowY(a) + (rowY(r) - rowY(a)) * (hold ? 0.85 : 0.15);
          return (
            <g key={`${e.kind}-${e.actor}-${e.resource}`} className={`redge ${e.kind}${e.cycle ? " cycle" : ""}`}
              data-testid={`edge-${e.kind}`}>
              <path d={curve(a, r, e.kind === "holds")}
                markerEnd={e.kind === "member" ? undefined : `url(#arrow-${kind})`} />
              <text x={hold ? W - BOX_W - 48 : BOX_W + 48} y={y - 5}
                textAnchor={hold ? "end" : "start"}>{e.label}</text>
            </g>
          );
        })}
        {g.actors.map((id, i) => {
          const t = world.threads[id];
          return (
            <g key={id} className="rnode actor" data-selected={isSel(id)}
              data-testid="actor-node" transform={`translate(20 ${rowY(i) - BOX_H / 2})`}
              onClick={() => pick("thread", id)}>
              <rect width={BOX_W} height={BOX_H} rx="8" />
              <circle cx="14" cy={BOX_H / 2} r="5" fill={STATUS_COLOR[t.status]} />
              <text x="28" y="19" className="title">{t.name}</text>
              <text x="28" y="35" className="sub">
                {t.kind} · {t.status}{t.basis === "inferred" ? " (inferred)" : ""}
              </text>
            </g>
          );
        })}
        {g.resources.map((id, i) => {
          const [kind, text] = describe(replay, world, id);
          const sync = id in world.syncs;
          return (
            <g key={id} className="rnode resource" data-selected={isSel(id)}
              data-testid="resource-node"
              transform={`translate(${W - BOX_W - 20} ${rowY(i) - BOX_H / 2})`}
              onClick={() => pick(sync ? "sync" : "queue", id)}>
              <rect width={BOX_W} height={BOX_H} rx="8" />
              <text x="12" y="19" className="title">{name(id)}</text>
              <text x="12" y="35" className="sub">{kind} · {text}</text>
            </g>
          );
        })}
      </svg>
      <p className="muted rlegend">
        Solid line: holds. Dashed line: waits. Click a box to inspect it.
      </p>
    </div>
  );
}
