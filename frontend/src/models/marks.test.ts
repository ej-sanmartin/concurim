import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { objectColor } from "../animations/palette";
import { buildMarkIndex, marksAt } from "./marks";
import type { Replay } from "./replay";
import { buildStates } from "./states";

// Real capture of samples/thread_pool.py, recorded with source included.
const replay: Replay = JSON.parse(
  readFileSync(
    new URL("../../tests/fixtures/thread-pool-sample.replay.json", import.meta.url),
    "utf8",
  ),
);
const states = buildStates(replay);
const index = buildMarkIndex(replay);
const at = (i: number) => marksAt(index, states[i], i);

describe("code marks", () => {
  it("shows busy workers in the colour of the item they hold", () => {
    const i = replay.events.findIndex((e) => e.event_type === "executor.task.started");
    const busy = at(i + 1);
    expect(busy.length).toBeGreaterThan(0);
    const m = busy[0];
    expect(replay.source_paths).toContain(m.file);
    expect(m.line).toBeGreaterThan(0);
    const held = Object.values(states[i + 1].objects).find((o) => o.at === m.actor);
    if (held) expect(m.color).toBe(objectColor(held.id));
  });

  it("clears a worker when its task finishes and at the very start", () => {
    expect(at(0)).toEqual([]);
    const last = replay.events.length - 1;
    // Only the main thread is still running; no pool task is marked.
    expect(at(last).map((m) => m.fn)).toEqual(["main"]);
  });
});
