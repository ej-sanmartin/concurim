import { describe, expect, it } from "vitest";
import { readCapture } from "./capture";

describe("readCapture", () => {
  it("is off without the capture flag", () => {
    expect(readCapture("?view=code")).toBeNull();
  });

  it("reads view, overlays and footer", () => {
    const c = readCapture("?capture=1&view=code&overlays=timeline&footer=hi")!;
    expect(c.view).toBe("code");
    expect([...c.overlays]).toEqual(["timeline"]);
    expect(c.footer).toBe("hi");
    expect(c.motionMs).toBe(0);
  });

  it("falls back to the animation for an unknown view", () => {
    expect(readCapture("?capture=1&view=nope")!.view).toBe("animation");
    expect(readCapture("?capture=1")!.overlays.size).toBe(0);
  });
});

describe("capture motion", () => {
  it("reads and clamps the glide time", () => {
    expect(readCapture("?capture=1&motion=400")!.motionMs).toBe(400);
    expect(readCapture("?capture=1&motion=99999")!.motionMs).toBe(2000);
    expect(readCapture("?capture=1&motion=-5")!.motionMs).toBe(0);
  });
});
