import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background, Controls, MarkerType, MiniMap, ReactFlow, ReactFlowProvider,
  ViewportPortal, useNodesState, useReactFlow, type Edge, type Node,
} from "@xyflow/react";
import type { Layout, Point } from "../models/layout";
import {
  GROUP_H_NODE, GROUP_W_NODE, NODE_H, NODE_W, SYNC_H, SYNC_W,
} from "../models/layout";
import {
  clearPositions, layoutKey, loadGrouped, loadHidden, loadPositions,
  saveGrouped, saveHidden, savePositions,
} from "../models/layoutStore";
import { actorOf, type Frame, type Replay, type TraceEvent } from "../models/replay";
import type { Selection } from "../models/selection";
import type { WorldState } from "../models/states";
import { FlowContext } from "./flowContext";
import { QUEUE_H, QueueNode, ThreadNode } from "./flowNodes";
import { FlowToolbar } from "./FlowToolbar";
import type { Geometry } from "./geometry";
import { GroupNode } from "./GroupNode";
import { SyncNode } from "./SyncNode";
import { Tokens } from "./Tokens";

const nodeTypes = {
  thread: ThreadNode, queue: QueueNode, sync: SyncNode, cluster: GroupNode,
};
const FIT = { padding: 0.18 };
/** Collapse worker groups by default when the graph is this crowded. */
const AUTO_GROUP_ACTORS = 24;
const groupId = (key: string) => `group:${key}`;
const size = (n: Node) =>
  n.type === "queue" ? { w: (n.data as { w: number }).w, h: QUEUE_H }
    : n.type === "sync" ? { w: SYNC_W, h: SYNC_H }
      : n.type === "cluster" ? { w: GROUP_W_NODE, h: GROUP_H_NODE }
        : { w: NODE_W, h: NODE_H };

/** Node objects from the automatic layout, overridden by saved positions. */
function buildNodes(layout: Layout, saved: Record<string, Point>): Node[] {
  const at = (id: string, c: Point, w: number, h: number) => {
    const p = saved[id] ?? c;
    return { x: p.x - w / 2, y: p.y - h / 2 };
  };
  const threads: Node[] = layout.threadOrder.map((id) => ({
    id, type: "thread", data: { role: layout.threads[id].role },
    position: at(id, layout.threads[id], NODE_W, NODE_H),
  }));
  const queues: Node[] = Object.entries(layout.queues).map(([id, q]) => ({
    id, type: "queue", data: { slots: q.slots, w: q.w },
    position: at(id, q, q.w, QUEUE_H),
  }));
  const syncs: Node[] = Object.entries(layout.syncs).map(([id, s]) => ({
    id, type: "sync", data: {}, position: at(id, s, SYNC_W, SYNC_H),
  }));
  const groups: Node[] = layout.groups.map((g) => ({
    id: groupId(g.key), type: "cluster", draggable: false,
    data: { members: g.members, role: g.role },
    position: at(groupId(g.key), g, GROUP_W_NODE, GROUP_H_NODE),
  }));
  return [...threads, ...queues, ...syncs, ...groups];
}

export interface FlowViewProps {
  replay: Replay;
  layout: Layout;
  world: WorldState;
  frame: Frame;
  event: TraceEvent;
  selection: Selection;
  onSelect: (s: Selection) => void;
  /** Milliseconds a token takes to glide between positions. */
  motionMs: number;
  theme: "dark" | "light";
  /** Increment to re-fit the graph (keyboard shortcut). */
  fitTick: number;
}

/**
 * Spatial view built on React Flow: draggable thread and queue nodes with
 * zoom/pan, plus a token layer for the data items. Dragging changes only
 * where nodes are drawn, never the trace.
 */
export function FlowView(props: FlowViewProps) {
  return (
    <ReactFlowProvider>
      <FlowInner {...props} />
    </ReactFlowProvider>
  );
}

function FlowInner(p: FlowViewProps) {
  const { replay, layout, world, frame, event, selection } = p;
  const key = useMemo(() => layoutKey(replay), [replay]);
  const [nodes, setNodes, onNodesChange] = useNodesState(
    useMemo(() => buildNodes(layout, loadPositions(key)), [layout, key]),
  );
  const [hidden, setHidden] = useState(() => new Set(loadHidden()));
  const [grouped, setGrouped] = useState(
    () => loadGrouped() ?? layout.threadOrder.length > AUTO_GROUP_ACTORS);
  const { fitView } = useReactFlow();
  const collapsed = grouped && layout.groups.length > 0;
  // Member id -> the node that stands for it (itself unless collapsed).
  const standIn = useMemo(() => {
    const out = new Map<string, string>();
    if (collapsed) {
      for (const g of layout.groups) g.members.forEach((m) => out.set(m, groupId(g.key)));
    }
    return out;
  }, [collapsed, layout]);
  const stand = useCallback((id: string) => standIn.get(id) ?? id, [standIn]);

  const centers = useMemo(() => {
    const out: Record<string, Point> = {};
    for (const n of nodes) {
      const { w, h } = size(n);
      out[n.id] = { x: n.position.x + w / 2, y: n.position.y + h / 2 };
    }
    return out;
  }, [nodes]);
  const geo: Geometry = useMemo(() => ({
    threads: Object.fromEntries(
      layout.threadOrder.map((id) => [id, centers[stand(id)]])),
    queues: Object.fromEntries(Object.entries(layout.queues).map(
      ([id, q]) => [id, { ...centers[id], slots: q.slots, w: q.w }])),
  }), [centers, layout, stand]);

  const hiddenIds = useMemo(() => {
    const ids = new Set<string>();
    const roleHidden = (id: string) => hidden.has(layout.threads[id].role);
    for (const id of layout.threadOrder) {
      if (roleHidden(id) || stand(id) !== id) ids.add(id);
    }
    for (const g of layout.groups) {
      if (!collapsed || g.members.every(roleHidden)) ids.add(groupId(g.key));
    }
    if (hidden.has("queue")) Object.keys(layout.queues).forEach((id) => ids.add(id));
    if (hidden.has("lock")) Object.keys(layout.syncs).forEach((id) => ids.add(id));
    return ids;
  }, [hidden, layout, collapsed, stand]);
  const shown = useMemo(
    () => nodes.map((n) => (hiddenIds.has(n.id) ? { ...n, hidden: true } : n)),
    [nodes, hiddenIds],
  );
  const edges: Edge[] = useMemo(() => {
    const make = (
      id: string, from: string, to: string, active: boolean, sourceHandle = "out",
      targetHandle = "in",
    ): Edge => ({
      id, source: stand(from), target: stand(to),
      sourceHandle, targetHandle,
      className: active ? "edge-active" : "edge-idle",
      markerEnd: {
        type: MarkerType.ArrowClosed, width: 16, height: 16,
        color: active ? "var(--accent)" : "var(--muted)",
      },
      hidden: hiddenIds.has(stand(from)) || hiddenIds.has(stand(to)),
    });
    const m = frame.motion;
    const queueEdges = layout.edges.map((e) => {
      const [from, to] = e.dir === "put" ? [e.thread, e.queue] : [e.queue, e.thread];
      return make(`${e.thread}-${e.queue}-${e.dir}`, from, to,
        !!m && m.from === from && m.to === to);
    });
    const syncEdges = layout.syncEdges.map((e) => make(
      `${e.thread}-${e.sync}-sync`, e.thread, e.sync,
      event.resource_id === e.sync && actorOf(event) === e.thread, "down"));
    const linkEdges = layout.syncLinks.map((l) => make(
      `${l.condition}-${l.lock}-link`, l.condition, l.lock,
      event.resource_id === l.condition, "side-out", "side-in"));
    // Collapsed groups merge many edges into one.
    const merged = new Map<string, Edge>();
    for (const e of [...queueEdges, ...syncEdges, ...linkEdges]) {
      const k = `${e.source}>${e.target}`;
      if (!merged.has(k) || e.className === "edge-active") merged.set(k, e);
    }
    return [...merged.values()];
  }, [layout, frame.motion, event, hiddenIds, stand]);

  const fit = useCallback(() => fitView({ ...FIT, duration: 300 }), [fitView]);
  const focusRaw = selection?.kind === "object"
    ? world.objects[selection.id]?.at : selection?.id;
  const focusId = focusRaw && stand(focusRaw);
  const focus = () => focusId && fitView(
    { nodes: [{ id: focusId }], duration: 300, maxZoom: 1.3, padding: 0.6 });
  const reset = () => {
    clearPositions(key);
    setNodes(buildNodes(layout, {}));
    window.setTimeout(fit, 30);
  };
  const toggle = (category: string) => setHidden((old) => {
    const next = new Set(old);
    if (!next.delete(category)) next.add(category);
    saveHidden([...next]);
    return next;
  });
  const toggleGroups = () => {
    saveGrouped(!grouped);
    setGrouped(!grouped);
    window.setTimeout(fit, 30);
  };
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    fit();
  }, [p.fitTick, fit]);

  const categories = [
    ...new Set(layout.threadOrder.map((id) => layout.threads[id].role as string)),
    ...(Object.keys(layout.queues).length ? ["queue"] : []),
    ...(Object.keys(layout.syncs).length ? ["lock"] : []),
    ...(Object.keys(replay.entities.objects).length ? ["item"] : []),
  ];
  const dragging = nodes.some((n) => n.dragging);
  // The dragged node comes from the event: ``centers`` may lag one frame.
  const saveCenters = (_: unknown, moved: Node) => {
    const { w, h } = size(moved);
    savePositions(key, {
      ...centers,
      [moved.id]: { x: moved.position.x + w / 2, y: moved.position.y + h / 2 },
    });
  };

  return (
    <FlowContext.Provider value={{ replay, world, frame, event, selection }}>
      <div className="flow" data-testid="flow">
        <FlowToolbar categories={categories} hidden={hidden} onToggle={toggle}
          onFit={fit} onReset={reset} onFocus={focus} canFocus={!!focusId}
          canGroup={layout.groups.length > 0} grouped={collapsed}
          onGroup={toggleGroups} />
        <ReactFlow
          nodes={shown} edges={edges} nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onNodeDragStop={saveCenters}
          onNodeClick={(e, n) => {
            e.stopPropagation();
            if (n.type === "cluster") return;
            p.onSelect({ kind: n.type as "thread" | "queue" | "sync", id: n.id });
          }}
          onPaneClick={() => p.onSelect(null)}
          fitView fitViewOptions={FIT} minZoom={0.25} maxZoom={2.5}
          nodesConnectable={false} elementsSelectable={false}
          nodeDragThreshold={4} zoomOnDoubleClick={false}
          deleteKeyCode={null} selectionKeyCode={null}
          multiSelectionKeyCode={null} disableKeyboardA11y
          colorMode={p.theme} aria-label="Threads, queues and locks"
        >
          <Background gap={28} size={1.2} color="var(--border)" />
          <Controls showInteractive={false} showFitView={false} position="bottom-right" />
          {shown.filter((n) => !n.hidden).length > 10 && <MiniMap pannable zoomable />}
          {!hidden.has("item") && (
            <ViewportPortal>
              <Tokens world={world} geo={geo} selection={selection}
                motionMs={dragging ? 0 : p.motionMs} onSelect={p.onSelect} />
            </ViewportPortal>
          )}
        </ReactFlow>
      </div>
    </FlowContext.Provider>
  );
}
