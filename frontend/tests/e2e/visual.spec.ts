import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

// Deterministic: the committed real capture is injected in place of the
// live demo recording, and motion is disabled.
const FIXTURE = fileURLToPath(
  new URL("../fixtures/pipeline.replay.json", import.meta.url),
);

async function open(page: Page, theme: "dark" | "light", eventNo: number) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/replay", (r) => r.fulfill({ path: FIXTURE }));
  await page.addInitScript((t) => localStorage.setItem("concurim-theme", t), theme);
  await page.goto("/");
  await page.getByTestId("flow").waitFor();
  await page.getByTestId("goto").fill(String(eventNo));
  await page.waitForTimeout(200);
}

for (const [theme, eventNo] of [["dark", 41], ["light", 101]] as const) {
  test(`visual: ${theme} theme at event ${eventNo}`, async ({ page }) => {
    await open(page, theme, eventNo);
    await expect(page).toHaveScreenshot(`${theme}-${eventNo}.png`);
  });
}
