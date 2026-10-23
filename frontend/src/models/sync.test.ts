import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { computeLayout } from "./layout";
import type { Replay } from "./replay";
import { buildStates } from "./states";

// Fixed conversions of the bundled recordings (scripts/make_fixtures.py).
const load = (name: string): Replay =>
  JSON.parse(readFileSync(
    new URL(`../../tests/fixtures/${name}-sample.replay.json`, import.meta.url),
    "utf8"));

describe("locks and semaphores", () => {
  const replay = load("lock-contention");
  const states = buildStates(replay);

  it("places each lock in the band below the threads", () => {
    const layout = computeLayout(replay);
    const lockIds = Object.keys(replay.entities.syncs);
    expect(lockIds.length).toBeGreaterThan(0);
    for (const id of lockIds) {
      for (const t of layout.threadOrder) {
        expect(layout.syncs[id].y).toBeGreaterThan(layout.threads[t].y);
      }
    }
    expect(layout.syncEdges.length).toBeGreaterThan(0);
  });

  it("never shows two holders of a plain lock", () => {
    for (const s of states) {
      for (const sync of Object.values(s.syncs)) {
        if (sync.kind === "lock") expect(sync.holders.length).toBeLessThanOrEqual(1);
      }
    }
  });

  it("holds never exceed semaphore capacity", () => {
    const sem = load("semaphore");
    for (const s of buildStates(sem)) {
      for (const x of Object.values(s.syncs)) {
        expect(x.holders.length).toBeLessThanOrEqual(x.capacity);
        expect(x.value + x.holders.length).toBe(x.capacity);
      }
    }
  });
});

describe("executors and tasks", () => {
  it("draws a thread pool as a queue that workers get tasks from", () => {
    const replay = load("thread-pool");
    const layout = computeLayout(replay);
    const [pool] = Object.values(replay.entities.queues);
    expect(pool.kind).toBe("executor");
    expect(pool.workers).toBeGreaterThan(0);
    const roles = new Set(Object.values(layout.threads).map((t) => t.role));
    expect(roles.has("consumer")).toBe(true);
  });

  it("treats asyncio tasks as actors and runs one at a time", () => {
    const replay = load("asyncio-tasks");
    const tasks = Object.values(replay.entities.threads).filter((t) => t.kind === "task");
    expect(tasks.length).toBeGreaterThan(1);
    for (const s of buildStates(replay)) {
      const running = Object.values(s.threads).filter(
        (t) => t.kind === "task" && t.status === "running");
      expect(running.length).toBeLessThanOrEqual(1);
    }
  });
});
