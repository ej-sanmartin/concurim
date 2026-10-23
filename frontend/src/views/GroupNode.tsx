import type { Node, NodeProps } from "@xyflow/react";
import { Handle, Position } from "@xyflow/react";
import { STATUS_COLOR } from "../animations/palette";
import { GROUP_H_NODE, GROUP_W_NODE } from "../models/layout";
import { useFlow } from "./flowContext";

export type GroupNodeType = Node<{ members: string[]; role: string }, "cluster">;

/** Many similar workers drawn as one node with a status summary. */
export function GroupNode({ data }: NodeProps<GroupNodeType>) {
  const { world, replay } = useFlow();
  const counts = new Map<string, number>();
  for (const id of data.members) {
    const st = world.threads[id]?.status ?? "unseen";
    counts.set(st, (counts.get(st) ?? 0) + 1);
  }
  const kinds = new Set(data.members.map((m) => replay.entities.threads[m].kind));
  const noun = kinds.size === 1 && kinds.has("task") ? "tasks" : "threads";
  return (
    <div className="fnode group" data-testid="group"
      style={{ width: GROUP_W_NODE, height: GROUP_H_NODE }}>
      <Handle type="target" position={Position.Left} id="in" isConnectable={false} />
      <Handle type="source" position={Position.Right} id="out" isConnectable={false} />
      <Handle type="source" position={Position.Bottom} id="down" isConnectable={false} />
      <span className="tiny">{data.role} group</span>
      <b className="node-title">{data.members.length} {noun}</b>
      <span className="group-counts">
        {[...counts].map(([st, n]) => (
          <span key={st} className="node-sub" title={st}>
            <i className="dot" style={{ background: STATUS_COLOR[st as keyof typeof STATUS_COLOR] ?? "var(--c-idle)" }} />
            {n} {st}
          </span>
        ))}
      </span>
    </div>
  );
}
