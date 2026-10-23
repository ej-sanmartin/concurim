import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background, Controls, MarkerType, MiniMap, ReactFlow, ReactFlowProvider,
  ViewportPortal, useNodesState, useReactFlow, type Edge, type Node,
} from "@xyflow/react";
import type { Layout, Point } from "../models/layout";
import { NODE_H, NODE_W } from "../models/layout";
import {
  clearPositions, layoutKey, loadHidden, loadPositions, saveHidden, savePositions,
} from "../models/layoutStore";
import type { Frame, Replay, TraceEvent } from "../models/replay";
import type { Selection } from "../models/selection";
import type { WorldState } from "../models/states";
import { FlowContext } from "./flowContext";
import { QUEUE_H, QueueNode, ThreadNode } from "./flowNodes";
import { FlowToolbar } from "./FlowToolbar";
import type { Geometry } from "./geometry";
import { Tokens } from "./Tokens";

const nodeTypes = { thread: ThreadNode, queue: QueueNode };
const FIT = { padding: 0.18 };
const size = (n: Node) =>
  n.type === "queue"
    ? { w: (n.data as { w: number }).w, h: QUEUE_H }
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
  return [...threads, ...queues];
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
  const { fitView } = useReactFlow();

  const centers = useMemo(() => {
    const out: Record<string, Point> = {};
    for (const n of nodes) {
      const { w, h } = size(n);
      out[n.id] = { x: n.position.x + w / 2, y: n.position.y + h / 2 };
    }
    return out;
  }, [nodes]);
  const geo: Geometry = useMemo(() => ({
    threads: Object.fromEntries(layout.threadOrder.map((id) => [id, centers[id]])),
    queues: Object.fromEntries(Object.entries(layout.queues).map(
      ([id, q]) => [id, { ...centers[id], slots: q.slots, w: q.w }])),
  }), [centers, layout]);

  const hiddenIds = useMemo(() => {
    const ids = new Set<string>();
    for (const id of layout.threadOrder) {
      if (hidden.has(layout.threads[id].role)) ids.add(id);
    }
    if (hidden.has("queue")) Object.keys(layout.queues).forEach((id) => ids.add(id));
    return ids;
  }, [hidden, layout]);
  const shown = useMemo(
    () => nodes.map((n) => (hiddenIds.has(n.id) ? { ...n, hidden: true } : n)),
    [nodes, hiddenIds],
  );
  const edges: Edge[] = useMemo(() => layout.edges.map((e) => {
    const put = e.dir === "put";
    const [source, target] = put ? [e.thread, e.queue] : [e.queue, e.thread];
    const m = frame.motion;
    const active = !!m && m.from === source && m.to === target;
    return {
      id: `${e.thread}-${e.queue}-${e.dir}`, source, target,
      sourceHandle: "out", targetHandle: "in",
      className: active ? "edge-active" : "edge-idle",
      markerEnd: {
        type: MarkerType.ArrowClosed, width: 16, height: 16,
        color: active ? "var(--accent)" : "var(--muted)",
      },
      hidden: hiddenIds.has(source) || hiddenIds.has(target),
    };
  }), [layout, frame.motion, hiddenIds]);

  const fit = useCallback(() => fitView({ ...FIT, duration: 300 }), [fitView]);
  const focusId = selection?.kind === "object"
    ? world.objects[selection.id]?.at : selection?.id;
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
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    fit();
  }, [p.fitTick, fit]);

  const categories = [
    ...new Set(layout.threadOrder.map((id) => layout.threads[id].role as string)),
    ...(Object.keys(layout.queues).length ? ["queue"] : []),
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
          onFit={fit} onReset={reset} onFocus={focus} canFocus={!!focusId} />
        <ReactFlow
          nodes={shown} edges={edges} nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onNodeDragStop={saveCenters}
          onNodeClick={(e, n) => {
            e.stopPropagation();
            p.onSelect({ kind: n.type as "thread" | "queue", id: n.id });
          }}
          onPaneClick={() => p.onSelect(null)}
          fitView fitViewOptions={FIT} minZoom={0.25} maxZoom={2.5}
          nodesConnectable={false} elementsSelectable={false}
          nodeDragThreshold={4} zoomOnDoubleClick={false}
          deleteKeyCode={null} selectionKeyCode={null}
          multiSelectionKeyCode={null} disableKeyboardA11y
          colorMode={p.theme} aria-label="Threads and queues"
        >
          <Background gap={28} size={1.2} color="var(--border)" />
          <Controls showInteractive={false} showFitView={false} position="bottom-right" />
          {nodes.length > 10 && <MiniMap pannable zoomable />}
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
