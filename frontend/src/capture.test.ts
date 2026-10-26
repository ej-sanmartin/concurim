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
  });

  it("falls back to the animation for an unknown view", () => {
    expect(readCapture("?capture=1&view=nope")!.view).toBe("animation");
    expect(readCapture("?capture=1")!.overlays.size).toBe(0);
  });
});
