import { describe, expect, it } from "vitest";
import type { ExportCaps } from "../api/types";
import {
  clipSeconds, defaultForm, formatSeconds, problem, toRequest,
} from "./options";

const caps = (over: Partial<ExportCaps> = {}): ExportCaps => ({
  browser: true, ffmpeg: true, problems: {}, formats: [], video_formats: [],
  views: [], overlays: [], themes: [], sizes: [], ...over,
});

describe("export form", () => {
  it("starts from the whole recording in the current view", () => {
    const f = defaultForm("code", 31, caps());
    expect([f.view, f.start, f.end, f.format]).toEqual(["code", 1, 31, "mp4"]);
  });

  it("falls back to PNG frames when ffmpeg is missing", () => {
    expect(defaultForm("animation", 9, caps({ ffmpeg: false })).format)
      .toBe("png");
  });

  it("builds the request: overlays by toggle, glide by switch", () => {
    const f = { ...defaultForm("animation", 10, caps()), timeline: false };
    const r = toRequest(f);
    expect(r.overlays).toEqual(["explanation"]);
    expect(r.motion_ms).toBe(400);
    expect(toRequest({ ...f, smooth: false }).motion_ms).toBe(0);
  });

  it("explains what blocks an export", () => {
    const f = defaultForm("animation", 10, caps());
    expect(problem(f, 10, caps())).toBeNull();
    expect(problem({ ...f, end: 11 }, 10, caps())).toMatch(/1 to 10/);
    expect(problem({ ...f, start: 5, end: 4 }, 10, caps())).toMatch(/first/);
    expect(problem(f, 10, caps({ browser: false, problems: { browser: "no browser" } })))
      .toBe("no browser");
    expect(problem(f, 10, caps({ ffmpeg: false }))).toMatch(/ffmpeg/);
    expect(problem({ ...f, format: "png" }, 10, caps({ ffmpeg: false }))).toBeNull();
  });

  it("estimates the clip length", () => {
    const f = { ...defaultForm("animation", 31, caps()), hold: 1.2 };
    expect(clipSeconds(f)).toBeCloseTo(37.2);
    expect(formatSeconds(37.2)).toBe("37 s");
    expect(formatSeconds(125)).toBe("2:05");
  });
});
