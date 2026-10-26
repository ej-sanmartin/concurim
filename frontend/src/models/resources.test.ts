import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { buildResourceGraph } from "./resources";
import type { Replay } from "./replay";
import { buildStates } from "./states";

const load = (name: string): Replay =>
  JSON.parse(readFileSync(
    new URL(`../../tests/fixtures/${name}-sample.replay.json`, import.meta.url),
    "utf8"));

describe("resource graph", () => {
  it("finds the circular lock wait and only while both threads wait", () => {
    const replay = load("lock-order");
    const states = buildStates(replay);
    const graphs = states.map((w) => buildResourceGraph(w));
    const bad = graphs.filter((g) => g.cycle.length > 0);
    expect(bad.length).toBeGreaterThan(0);
    for (const g of bad) {
      expect(g.cycle.length).toBe(2);
      expect(g.edges.filter((e) => e.cycle && e.kind === "waits").length).toBe(2);
      expect(g.edges.filter((e) => e.cycle && e.kind === "holds").length).toBe(2);
    }
    expect(graphs[graphs.length - 1].cycle).toEqual([]);
  });

  it("shows plain contention as waits without calling it a cycle", () => {
    const replay = load("lock-contention");
    const graphs = buildStates(replay).map((w) => buildResourceGraph(w));
    expect(graphs.some((g) => g.edges.some((e) => e.kind === "waits"))).toBe(true);
    expect(graphs.every((g) => g.cycle.length === 0)).toBe(true);
  });

  it("does not claim a cycle for semaphore waits", () => {
    const replay = load("semaphore");
    const graphs = buildStates(replay).map((w) => buildResourceGraph(w));
    expect(graphs.every((g) => g.cycle.length === 0)).toBe(true);
  });

  it("ties task group members to the group", () => {
    const replay = load("task-group");
    const graphs = buildStates(replay).map((w) => buildResourceGraph(w));
    expect(Math.max(...graphs.map((g) => g.edges.filter((e) => e.kind === "member").length)))
      .toBe(3);
  });
});
