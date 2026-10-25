import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { objectColor } from "../animations/palette";
import { buildMarkIndex, marksAt, shadesByLine } from "./marks";
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

describe("code marks inside a function", () => {
  const start = replay.events.findIndex((e) => e.event_type === "executor.task.started");
  const src = replay.events[start].source!;
  const actor = replay.events[start].thread_id!;
  const span: [number, number] = [src.line, src.line + 5];
  const withRanges = { ...replay, code_ranges: { [src.file]: [span] } };
  const marksFor = (r: Replay, i: number) =>
    marksAt(buildMarkIndex(r), states[i], i).filter((m) => m.actor === actor);

  it("shades the whole body until the worker is seen somewhere inside", () => {
    const [m] = marksFor(withRanges, start);
    expect([m.exact, m.sampled, m.range]).toEqual([false, false, span]);
    const shades = shadesByLine([m]);
    for (let l = span[0]; l <= span[1]; l++) {
      expect(shades.get(l)).toEqual([{ color: m.color, shade: "body" }]);
    }
    expect(shades.has(span[1] + 1)).toBe(false);
  });

  it("keeps the old single-line mark when the trace has no ranges", () => {
    const [m] = marksFor({ ...replay, code_ranges: undefined }, start);
    expect([m.exact, m.range]).toEqual([true, undefined]);
    expect([...shadesByLine([m]).keys()]).toEqual([src.line]);
  });

  it("follows a sampled line and softly shades the rest of the function", () => {
    const line = src.line + 2;
    const sampled = {
      ...withRanges,
      line_samples: [
        { at: start, actor, file: src.file, line, function: src.function },
      ],
    };
    const [m] = marksFor(sampled, start);
    expect([m.line, m.exact, m.sampled]).toEqual([line, true, true]);
    const shades = shadesByLine([m]);
    expect(shades.get(line)?.[0].shade).toBe("line");
    expect(shades.get(span[0])?.[0].shade).toBe("context");
  });

  it("ignores a sample taken just as the task finished", () => {
    const end = replay.events.findIndex(
      (e, i) => i > start && e.event_type === "executor.task.finished"
        && e.thread_id === actor,
    );
    const stale = {
      ...withRanges,
      line_samples: [
        { at: end, actor, file: src.file, line: src.line + 1, function: src.function },
      ],
    };
    expect(marksFor(stale, end)).toEqual([]);
  });
});
