import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { describeDifferences, summarize } from "./compare";
import type { Replay } from "./replay";

const load = (name: string): Replay =>
  JSON.parse(readFileSync(
    new URL(`../../tests/fixtures/${name}-sample.replay.json`, import.meta.url),
    "utf8"));

describe("run comparison", () => {
  it("measures observed work overlap from work spans only", () => {
    const pool = summarize(load("thread-pool"), "pool");
    expect(pool.maxOverlap).toBeGreaterThan(1);
    expect(pool.busyNs).toBeGreaterThan(0);
    const locks = summarize(load("lock-contention"), "locks");
    expect(locks.busyNs).toBe(0);
    expect(locks.maxOverlap).toBe(0);
  });

  it("reads the interpreter facts that were recorded", () => {
    const run = summarize(load("thread-pool"), "a");
    expect(run.python).toMatch(/^3\./);
    expect(typeof run.gilEnabled === "boolean" || run.gilEnabled === null).toBe(true);
  });

  it("describes speed and GIL differences without claiming a cause", () => {
    const a = summarize(load("thread-pool"), "A");
    const b = { ...a, label: "B", durationNs: a.durationNs / 2, gilEnabled: !a.gilEnabled };
    const text = describeDifferences(a, b).join(" ");
    expect(text).toContain("2.00× faster");
    expect(text).toContain("GIL");
    expect(text).not.toMatch(/because|due to|caused/i);
  });

  it("warns when the programs differ", () => {
    const a = summarize(load("thread-pool"), "A");
    const b = summarize(load("semaphore"), "B");
    expect(describeDifferences(a, b)[0]).toContain("different programs");
  });
});
