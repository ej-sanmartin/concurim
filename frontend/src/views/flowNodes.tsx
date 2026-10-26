import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { STATUS_COLOR } from "../animations/palette";
import { NODE_H, NODE_W, SLOT_SIZE, type Role } from "../models/layout";
import { nameOf } from "../models/names";
import { actorOf, type Replay, type ThreadState } from "../models/replay";
import { useFlow } from "./flowContext";

export const QUEUE_H = 68;

export type ThreadNodeType = Node<{ role: Role }, "thread">;
export type QueueNodeType = Node<{ slots: number; w: number }, "queue">;

/** Hidden connection points: edges attach at the left and right middle. */
function Handles() {
  return (
    <>
      <Handle type="target" position={Position.Left} id="in" isConnectable={false} />
      <Handle type="source" position={Position.Right} id="out" isConnectable={false} />
    </>
  );
}

const WAIT_VERB: Record<string, string> = {
  put: "put on", get: "get from", join: "join", acquire: "acquire",
  wait: "be woken by",
};

function waitText(s: ThreadState, replay: Replay): string {
  if (s.status === "waiting" && s.waiting_on) {
    const verb = WAIT_VERB[s.waiting_on.op] ?? s.waiting_on.op;
    return `waiting to ${verb} ${nameOf(replay, s.waiting_on.resource)}`;
  }
  if (s.status === "working") return `working: ${s.work ?? ""}`;
  if (s.status === "running") return "running (not blocked)";
  if (s.status === "suspended") return "suspended (awaiting)";
  return s.status;
}

/** A thread: its observed status and what it is waiting for. */
export function ThreadNode({ id, data }: NodeProps<ThreadNodeType>) {
  const { world, replay, event, selection } = useFlow();
  const state = world.threads[id];
  const color = state ? STATUS_COLOR[state.status] : "var(--c-idle)";
  return (
    <div
      className="fnode thread" data-testid="thread"
      data-thread={replay.entities.threads[id].name}
      data-status={state?.status ?? "unseen"}
      data-active={actorOf(event) === id || undefined}
      data-selected={(selection?.kind === "thread" && selection.id === id) || undefined}
      data-inferred={state?.basis === "inferred" || undefined}
      style={{ width: NODE_W, height: NODE_H, borderColor: color, opacity: state ? 1 : 0.4 }}
    >
      <Handles />
      <Handle type="source" position={Position.Bottom} id="down" isConnectable={false} />
      <span className="tiny">
        {replay.entities.threads[id].kind === "thread"
          ? data.role : `${replay.entities.threads[id].kind} · ${data.role}`}
      </span>
      <span className="row">
        <i className={`dot${state?.status === "waiting" ? " pulse" : ""}`}
          style={{ background: color }} />
        <b className="node-title" title={replay.entities.threads[id].name}>
          {replay.entities.threads[id].name}
        </b>
      </span>
      <span className="node-sub" title={state ? waitText(state, replay) : undefined}>
        {state ? waitText(state, replay) : "not seen yet"}
      </span>
    </div>
  );
}

/** A queue, or an executor's pending tasks, drawn as slots; items are tokens. */
export function QueueNode({ id, data }: NodeProps<QueueNodeType>) {
  const { world, replay, event, selection } = useFlow();
  const info = replay.entities.queues[id];
  const state = world.queues[id];
  const size = state?.size ?? 0;
  const full = info.maxsize > 0 && size >= info.maxsize;
  const overflow = Math.max(0, size - data.slots);
  const cap = info.maxsize > 0 ? String(info.maxsize) : "∞";
  const stats = info.kind === "executor"
    ? `${size} pending · ${state?.running ?? 0}/${info.workers} running`
    : `${size} / ${cap} queued · ${state?.unfinished ?? 0} unfinished`;
  return (
    <div
      className="fnode queue" data-testid={info.kind === "executor" ? "executor" : "queue"}
      data-active={event.resource_id === id || undefined}
      data-selected={(selection?.kind === "queue" && selection.id === id) || undefined}
      data-full={full || undefined}
      data-shutdown={state?.shutdown ?? undefined}
      style={{ width: data.w, height: QUEUE_H }}
    >
      <Handles />
      <span className="q-title node-title" title={info.name}>
        {info.name}
      </span>
      <span className="q-front tiny">front →</span>
      {Array.from({ length: data.slots }, (_, i) => (
        <span key={i} className="slot" style={{
          width: SLOT_SIZE - 10,
          left: data.w - 12 - SLOT_SIZE / 2 - i * SLOT_SIZE - (SLOT_SIZE - 10) / 2,
        }} />
      ))}
      {overflow > 0 && <span className="q-more node-sub">+{overflow}</span>}
      <span className="q-stats node-sub" data-testid="queue-stats">
        {stats}
      </span>
      {state?.shutdown && (
        <span className="q-badge badge-warn">
          {state.shutdown === "immediate" ? "shut down (immediate)" : "shut down"}
        </span>
      )}
    </div>
  );
}
