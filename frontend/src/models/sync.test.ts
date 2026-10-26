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

describe("events and conditions", () => {
  it("shows every runner waiting at a gate until the event is set", () => {
    const replay = load("event-gate");
    const [gate] = Object.values(replay.entities.syncs);
    expect(gate.kind).toBe("event");
    const states = buildStates(replay);
    const waiting = states.map((s) => s.syncs[gate.id]?.waiters.length ?? 0);
    expect(Math.max(...waiting)).toBe(3);
    const flag = states.map((s) => s.syncs[gate.id]?.is_set);
    expect(flag.indexOf(true)).toBeGreaterThan(waiting.indexOf(3) - 1);
    expect(computeLayout(replay).syncEdges.length).toBeGreaterThanOrEqual(3);
  });

  it("links a condition to its lock and keeps them side by side", () => {
    const replay = load("condition-mailbox");
    const layout = computeLayout(replay);
    expect(layout.syncLinks.length).toBe(1);
    const [{ condition, lock }] = layout.syncLinks;
    expect(replay.entities.syncs[condition].kind).toBe("condition");
    expect(layout.syncs[condition].x).toBeLessThan(layout.syncs[lock].x);
    expect(layout.syncs[condition].y).toBe(layout.syncs[lock].y);
  });

  it("never counts more notified waiters than are waiting", () => {
    for (const name of ["condition-mailbox", "asyncio-condition"]) {
      for (const s of buildStates(load(name))) {
        for (const x of Object.values(s.syncs)) {
          if (x.kind !== "condition") continue;
          expect(x.notified).toBeLessThanOrEqual(x.waiters.length);
        }
      }
    }
  });

  it("lets a notified waiter hold the lock only after the notifier released it", () => {
    const replay = load("condition-mailbox");
    const states = buildStates(replay);
    for (const s of states) {
      for (const x of Object.values(s.syncs)) {
        if (x.kind === "lock" || x.kind === "rlock") {
          expect(new Set(x.holders).size).toBeLessThanOrEqual(1);
        }
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

describe("task groups", () => {
  const replay = load("task-group");
  const [group] = Object.values(replay.entities.syncs);

  it("ties every member task and the parent to the group", () => {
    expect(group.kind).toBe("taskgroup");
    const linked = computeLayout(replay).syncEdges.filter((e) => e.sync === group.id);
    expect(new Set(linked.map((e) => e.thread)).size).toBe(4);
  });

  it("counts unfinished members down to zero and shows the parent waiting", () => {
    const states = buildStates(replay);
    const running = states.map((s) => s.syncs[group.id]?.running ?? 0);
    expect(Math.max(...running)).toBe(3);
    expect(running[running.length - 1]).toBe(0);
    expect(states.some((s) => s.syncs[group.id]?.waiters.length === 1)).toBe(true);
  });
});
