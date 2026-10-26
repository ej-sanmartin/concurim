import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { ancestors, familyRows, hasLineage, lineageRoots, rootOf } from "./lineage";
import type { Replay } from "./replay";

const load = (name: string): Replay =>
  JSON.parse(readFileSync(
    new URL(`../../tests/fixtures/${name}-sample.replay.json`, import.meta.url),
    "utf8"));

describe("lineage", () => {
  const replay = load("lineage-pipeline");

  it("walks a word count back to its page through the sentence", () => {
    expect(hasLineage(replay)).toBe(true);
    const leaf = Object.values(replay.entities.objects)
      .find((o) => ancestors(replay, o.id).length === 2)!;
    const up = ancestors(replay, leaf.id);
    expect(replay.entities.objects[up[1]].parent).toBeNull();
    expect(rootOf(replay, leaf.id)).toBe(up[1]);
  });

  it("lists one family per page and flags relatives of the focus", () => {
    expect(lineageRoots(replay).length).toBe(2);
    const leaf = Object.values(replay.entities.objects)
      .find((o) => ancestors(replay, o.id).length === 2)!;
    const rows = familyRows(replay, leaf.id);
    expect(rows.map((r) => r.depth)).toEqual([0, 1, 2, 1, 2]);
    expect(rows.filter((r) => r.related).map((r) => r.id))
      .toEqual([rootOf(replay, leaf.id), ancestors(replay, leaf.id)[0], leaf.id]);
  });

  it("does not loop on a cycle or break on an unknown parent", () => {
    const odd = structuredClone(replay);
    const [a, b] = Object.keys(odd.entities.objects);
    odd.entities.objects[a].parent = b;
    odd.entities.objects[b].parent = a;
    expect(ancestors(odd, a).length).toBeLessThanOrEqual(2);
    expect(familyRows(odd, a).length).toBeGreaterThan(0);
    odd.entities.objects[a].parent = "object-404";
    expect(familyRows(odd, a).some((r) => !r.known)).toBe(true);
  });

  it("reports no lineage when no item was derived", () => {
    expect(hasLineage(load("lock-contention"))).toBe(false);
  });
});
