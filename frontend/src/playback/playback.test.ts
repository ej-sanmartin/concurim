import { describe, expect, it } from "vitest";
import type { TraceEvent } from "../models/replay";
import {
  IDLE_CAP_MS, MIN_REAL_DELAY_MS, clampIndex, delayBefore, realDelay, stepDelay,
} from "./stepping";
import { findEvent, nextBlocking, nextForSelection } from "./navigation";

const ev = (type: string, ms: number, extra: Partial<TraceEvent> = {}): TraceEvent => ({
  schema_version: 1, event_id: `e-${type}-${ms}`, event_type: type,
  timestamp_ns: ms * 1e6, sequence: ms, process_id: 1, ...extra,
});

const events = [
  ev("thread.started", 0, { thread_id: "t1" }),
  ev("queue.put.completed", 5, { thread_id: "t1", resource_id: "q1", object_id: "o1" }),
  ev("queue.get.blocked", 10, { thread_id: "t2", resource_id: "q1" }),
  ev("queue.get.completed", 2000, { thread_id: "t2", resource_id: "q1", object_id: "o1" }),
  ev("queue.put.blocked", 2001, { thread_id: "t1", resource_id: "q2" }),
  ev("queue.shutdown.requested", 2002, { thread_id: "t1", resource_id: "q1" }),
];

describe("explanatory pacing", () => {
  it("dwells longer on blocking and shutdown than on ordinary events", () => {
    const ordinary = stepDelay(events[1], 1);
    expect(stepDelay(events[2], 1)).toBeGreaterThan(ordinary);
    expect(stepDelay(events[5], 1)).toBeGreaterThan(ordinary);
  });
  it("skips quickly over events with no visual effect", () => {
    expect(stepDelay(ev("queue.put.started", 1), 1)).toBeLessThan(stepDelay(events[1], 1));
  });
  it("scales with speed", () => {
    expect(stepDelay(events[1], 2)).toBe(stepDelay(events[1], 1) / 2);
  });
});

describe("real-time pacing", () => {
  it("uses the recorded gap, scaled by speed", () => {
    expect(realDelay(events[0], events[1], 1, false)).toBe(MIN_REAL_DELAY_MS);
    expect(realDelay(events[2], events[3], 1, false)).toBe(1990);
    expect(realDelay(events[2], events[3], 2, false)).toBe(995);
  });
  it("compresses long idle gaps only when asked", () => {
    expect(realDelay(events[2], events[3], 1, true)).toBe(IDLE_CAP_MS);
    expect(realDelay(events[0], events[1], 1, true)).toBe(MIN_REAL_DELAY_MS);
  });
  it("is chosen by delayBefore according to the pace", () => {
    expect(delayBefore(events, 2, 1, "realtime", false)).toBe(1990);
    expect(delayBefore(events, 2, 1, "explain", false)).toBe(stepDelay(events[3], 1));
  });
});

describe("navigation", () => {
  it("finds the next and previous blocking event", () => {
    expect(nextBlocking(events, 0)).toBe(2);
    expect(nextBlocking(events, 2)).toBe(4);
    expect(nextBlocking(events, 4)).toBeNull();
    expect(nextBlocking(events, 4, -1)).toBe(2);
    expect(nextBlocking(events, 2, -1)).toBeNull();
  });
  it("jumps between events of the selected resource", () => {
    const q2 = { kind: "queue", id: "q2" } as const;
    expect(nextForSelection(events, 0, q2)).toBe(4);
    const obj = { kind: "object", id: "o1" } as const;
    expect(nextForSelection(events, 1, obj)).toBe(3);
    expect(nextForSelection(events, 3, obj)).toBeNull();
    const thread = { kind: "thread", id: "t2" } as const;
    expect(nextForSelection(events, 2, thread)).toBe(3);
    expect(nextForSelection(events, 0, null)).toBeNull();
  });
  it("does not run off either end", () => {
    expect(findEvent(events, 5, 1, () => true)).toBeNull();
    expect(findEvent(events, 0, -1, () => true)).toBeNull();
    expect(clampIndex(99, events.length)).toBe(5);
    expect(clampIndex(-3, events.length)).toBe(0);
  });
});
