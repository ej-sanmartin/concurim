import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { SYNC_H, SYNC_W } from "../models/layout";
import { nameOf } from "../models/names";
import type { Replay, SyncKind, SyncState } from "../models/replay";
import { useFlow } from "./flowContext";

export type SyncNodeType = Node<Record<string, never>, "sync">;

export const KIND_LABEL: Record<SyncKind, string> = {
  lock: "lock", rlock: "reentrant lock", semaphore: "semaphore",
  event: "event", condition: "condition", barrier: "barrier",
  taskgroup: "task group",
};

interface Summary {
  text: string;
  busy: boolean;
}

/** One line of state, and whether the resource is currently contended. */
export function summarize(
  kind: SyncKind, info: { capacity: number; lock: string | null },
  state: SyncState | undefined, replay: Replay,
): Summary {
  const waiting = state?.waiters.length ?? 0;
  if (kind === "event") {
    const set = state?.is_set ?? false;
    return { text: set ? "set" : "not set", busy: !set && waiting > 0 };
  }
  if (kind === "barrier") {
    const parties = info.capacity;
    if (state?.broken) return { text: "broken", busy: false };
    return {
      text: waiting > 0 ? `${waiting} of ${parties} waiting` : "open",
      busy: waiting > 0,
    };
  }
  if (kind === "condition") {
    const notified = state?.notified ?? 0;
    const lock = info.lock ? ` · lock: ${nameOf(replay, info.lock)}` : "";
    return {
      text: `${waiting} waiting${notified ? ` · ${notified} notified` : ""}${lock}`,
      busy: waiting > 0,
    };
  }
  if (kind === "taskgroup") {
    const total = state?.members.length ?? 0;
    const running = state?.running ?? 0;
    return { text: `${running} of ${total} tasks running`, busy: running > 0 };
  }
  const holders = state?.holders ?? [];
  const free = state ? state.value : info.capacity;
  if (kind === "semaphore") {
    return { text: `${free} / ${info.capacity} permits free`, busy: free === 0 };
  }
  const who = [...new Set(holders)].map((h) => nameOf(replay, h)).join(", ");
  return {
    text: holders.length === 0
      ? "free"
      : `held by ${who}${holders.length > 1 ? ` ×${holders.length}` : ""}`,
    busy: holders.length > 0,
  };
}

/**
 * A lock, semaphore, event, condition, barrier or task group: its state,
 * and who is waiting for it. Conditions link to their lock through the
 * side handles.
 */
export function SyncNode({ id }: NodeProps<SyncNodeType>) {
  const { world, replay, event, selection } = useFlow();
  const info = replay.entities.syncs[id];
  const state = world.syncs[id];
  const free = state ? state.value : info.capacity;
  const { text, busy } = summarize(info.kind, info, state, replay);
  const waiting = state?.waiters.length ?? 0;
  return (
    <div
      className="fnode sync" data-testid="sync" data-sync={info.name}
      data-kind={info.kind} data-busy={busy || undefined}
      data-set={(info.kind === "event" && state?.is_set) || undefined}
      data-active={event.resource_id === id || undefined}
      data-selected={(selection?.kind === "sync" && selection.id === id) || undefined}
      style={{ width: SYNC_W, height: SYNC_H }}
    >
      <Handle type="target" position={Position.Top} id="in" isConnectable={false} />
      <Handle type="source" position={Position.Right} id="side-out" isConnectable={false} />
      <Handle type="target" position={Position.Left} id="side-in" isConnectable={false} />
      <span className="tiny">{KIND_LABEL[info.kind]}</span>
      <b className="node-title">{info.name}</b>
      {info.kind === "semaphore" && (
        <span className="permits" aria-hidden>
          {Array.from({ length: Math.min(info.capacity, 12) }, (_, i) => (
            <i key={i} data-taken={i >= free || undefined} />
          ))}
        </span>
      )}
      <span className="node-sub" title={text} data-testid="sync-stats">{text}</span>
      {waiting > 0 && info.kind !== "condition" && (
        <span className="badge-warn">{waiting} waiting</span>
      )}
    </div>
  );
}
