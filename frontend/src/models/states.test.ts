import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { computeLayout, slotPoint } from "./layout";
import type { Replay } from "./replay";
import { buildStates, EMPTY_WORLD, indexAtTime } from "./states";

// Real capture of samples/threaded_pipeline.py (scripts/make_fixtures.py).
const replay: Replay = JSON.parse(
  readFileSync(
    new URL("../../tests/fixtures/pipeline.replay.json", import.meta.url),
    "utf8",
  ),
);
const states = buildStates(replay);

function naiveFold(upTo: number) {
  const w = structuredClone(EMPTY_WORLD);
  for (const f of replay.frames.slice(0, upTo + 1)) {
    Object.assign(w.threads, f.changes.threads);
    Object.assign(w.queues, f.changes.queues);
    Object.assign(w.objects, f.changes.objects);
  }
  return w;
}

describe("replay states (real capture)", () => {
  it("has one state per event", () => {
    expect(states).toHaveLength(replay.events.length);
  });

  it("any index equals a from-scratch fold, so seeking backward is exact", () => {
    for (const i of [0, 1, 17, 40, 63, replay.events.length - 1]) {
      expect(states[i]).toEqual(naiveFold(i));
    }
  });

  it("never holds more items than capacity and keeps objects consistent", () => {
    for (const s of states) {
      for (const q of Object.values(s.queues)) {
        expect(q.size).toBeGreaterThanOrEqual(q.items.length);
        if (q.maxsize > 0) expect(q.size).toBeLessThanOrEqual(q.maxsize);
        for (const id of q.items) {
          expect(s.objects[id].phase).toBe("queued");
          expect(s.objects[id].at).toBe(q.id);
        }
      }
    }
  });

  it("distinguishes occupancy from unfinished tasks at some point", () => {
    const seen = states.some((s) =>
      Object.values(s.queues).some((q) => q.unfinished > q.size),
    );
    expect(seen).toBe(true);
  });

  it("ends drained, finished and shut down", () => {
    const last = states[states.length - 1];
    const q = Object.values(last.queues)[0];
    expect(q.size).toBe(0);
    expect(q.items).toEqual([]);
    expect(q.unfinished).toBe(0);
    expect(q.shutdown).toBe("graceful");
    for (const t of Object.values(last.threads)) {
      expect(["finished", "running"]).toContain(t.status);
    }
  });

  it("finds event indexes by timestamp", () => {
    const evs = replay.events;
    expect(indexAtTime(replay, -1)).toBe(0);
    expect(indexAtTime(replay, evs[30].timestamp_ns)).toBeGreaterThanOrEqual(30);
    expect(indexAtTime(replay, 1e18)).toBe(evs.length - 1);
  });
});

describe("layout", () => {
  const layout = computeLayout(replay);
  it("draws producers left of the queue and consumers right of it", () => {
    const q = Object.values(layout.queues)[0];
    for (const [id, p] of Object.entries(layout.threads)) {
      const name = replay.entities.threads[id].name;
      if (name.startsWith("producer")) expect(p.x).toBeLessThan(q.x);
      if (name.startsWith("consumer")) expect(p.x).toBeGreaterThan(q.x);
      if (name === "MainThread") expect(p.role).toBe("other");
    }
  });
  it("puts the queue front at the right-most slot", () => {
    const q = Object.values(layout.queues)[0];
    expect(slotPoint(q, 0).x).toBeGreaterThan(slotPoint(q, 1).x);
  });
});
