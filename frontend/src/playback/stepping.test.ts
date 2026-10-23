import { describe, expect, it } from "vitest";
import type { TraceEvent } from "../models/replay";
import { clampIndex, stepDelay } from "./stepping";

const ev = (event_type: string) => ({ event_type }) as TraceEvent;

describe("stepping", () => {
  it("dwells longer on visible events and scales with speed", () => {
    expect(stepDelay(ev("queue.put.completed"), 1)).toBeGreaterThan(
      stepDelay(ev("queue.put.started"), 1),
    );
    expect(stepDelay(ev("queue.put.completed"), 2)).toBe(
      stepDelay(ev("queue.put.completed"), 1) / 2,
    );
  });
  it("clamps seeks into range", () => {
    expect(clampIndex(-5, 10)).toBe(0);
    expect(clampIndex(99, 10)).toBe(9);
    expect(clampIndex(3.4, 10)).toBe(3);
  });
});
