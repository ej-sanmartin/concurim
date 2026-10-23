import { createContext, useContext } from "react";
import type { Frame, Replay, TraceEvent } from "../models/replay";
import type { Selection } from "../models/selection";
import type { WorldState } from "../models/states";

/** The replayed state for the current event, shared with the graph nodes. */
export interface FlowCtx {
  replay: Replay;
  world: WorldState;
  frame: Frame;
  event: TraceEvent;
  selection: Selection;
}

export const FlowContext = createContext<FlowCtx | null>(null);

export function useFlow(): FlowCtx {
  const ctx = useContext(FlowContext);
  if (!ctx) throw new Error("FlowContext is missing");
  return ctx;
}
