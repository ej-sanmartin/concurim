import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { SYNC_H, SYNC_W } from "../models/layout";
import { nameOf } from "../models/names";
import { useFlow } from "./flowContext";

export type SyncNodeType = Node<Record<string, never>, "sync">;

const KIND_LABEL = { lock: "lock", rlock: "reentrant lock", semaphore: "semaphore" };

/** A lock or semaphore: who holds it and who is waiting for it. */
export function SyncNode({ id }: NodeProps<SyncNodeType>) {
  const { world, replay, event, selection } = useFlow();
  const info = replay.entities.syncs[id];
  const state = world.syncs[id];
  const holders = state?.holders ?? [];
  const waiting = state?.waiters.length ?? 0;
  const free = state ? state.value : info.capacity;
  const text = info.kind === "semaphore"
    ? `${free} / ${info.capacity} permits free`
    : holders.length === 0
      ? "free"
      : `held by ${[...new Set(holders)].map((h) => nameOf(replay, h)).join(", ")}`
        + (holders.length > 1 ? ` ×${holders.length}` : "");
  const busy = info.kind === "semaphore" ? free === 0 : holders.length > 0;
  return (
    <div
      className="fnode sync" data-testid="sync" data-sync={info.name}
      data-kind={info.kind} data-busy={busy || undefined}
      data-active={event.resource_id === id || undefined}
      data-selected={(selection?.kind === "sync" && selection.id === id) || undefined}
      style={{ width: SYNC_W, height: SYNC_H }}
    >
      <Handle type="target" position={Position.Top} id="in" isConnectable={false} />
      <span className="tiny">{KIND_LABEL[info.kind]}</span>
      <b className="node-title">{info.name}</b>
      {info.kind === "semaphore" && (
        <span className="permits" aria-hidden>
          {Array.from({ length: Math.min(info.capacity, 12) }, (_, i) => (
            <i key={i} data-taken={i >= free || undefined} />
          ))}
        </span>
      )}
      <span className="node-sub" data-testid="sync-stats">{text}</span>
      {waiting > 0 && <span className="badge-warn">{waiting} waiting</span>}
    </div>
  );
}
