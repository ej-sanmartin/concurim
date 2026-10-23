import { describe, expect, it } from "vitest";
import { foldRows, FOLD_MIN } from "./fold";
import type { TraceEvent } from "./replay";

const ev = (type: string, resource?: string): TraceEvent => ({
  schema_version: 1, event_id: `${type}${resource}`, event_type: type,
  timestamp_ns: 0, sequence: 0, process_id: 1, resource_id: resource,
});
const cycle = () => [ev("get.started", "q"), ev("get.completed", "q"), ev("task.done", "q")];
const events = [
  ev("thread.started"), ...cycle(), ...cycle(), ...cycle(), ...cycle(),
  ev("lock.released", "l"), ev("lock.released", "l"),
];
const all = events.map((_, i) => i);

describe("foldRows", () => {
  it("folds a repeating pattern into one row with a repeat count", () => {
    const rows = foldRows(events, all, new Set(), -1);
    expect(rows.map((r) => r.index)).toEqual([0, 1, 13, 14]);
    expect(rows[1].fold).toEqual({ repeats: 4, period: 3, open: false });
    expect(rows[0].fold).toBeUndefined();
  });

  it("folds runs of one repeated event", () => {
    const same = [ev("a"), ev("a"), ev("a"), ev("a")];
    const rows = foldRows(same, [0, 1, 2, 3], new Set(), -1);
    expect(rows).toEqual([{ index: 0, fold: { repeats: 4, period: 1, open: false } }]);
  });

  it("leaves short repetition alone", () => {
    expect(FOLD_MIN).toBe(3);
    const two = [...cycle(), ...cycle()];
    expect(foldRows(two, two.map((_, i) => i), new Set(), -1)).toHaveLength(6);
  });

  it("opens a run on request and when the playhead is inside it", () => {
    expect(foldRows(events, all, new Set([1]), -1)).toHaveLength(15);
    const rows = foldRows(events, all, new Set(), 5);
    expect(rows[1].fold?.open).toBe(true);
    expect(rows).toHaveLength(15);
  });
});
