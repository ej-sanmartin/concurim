import { expect, test, type Page } from "@playwright/test";

// The export dialog, on a real recording (home server: samples).
test.use({ baseURL: "http://127.0.0.1:8798" });

async function open(page: Page, sample: string) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByTestId("home-screen").or(page.getByTestId("home")).first().waitFor();
  if (await page.getByTestId("home").isVisible()) await page.getByTestId("home").click();
  await page.getByTestId(`open-${sample}`).click();
  await page.getByTestId("flow").waitFor();
}

test("the export button opens a dialog whose options update the summary", async ({ page }) => {
  await open(page, "thread-pool");
  await page.getByTestId("open-export").click();
  const dialog = page.getByTestId("export-dialog");
  await expect(dialog).toBeVisible();
  const summary = page.getByTestId("export-summary");
  await expect(summary).toContainText("events");
  await page.getByTestId("export-start").fill("5");
  await page.getByTestId("export-end").fill("14");
  await expect(summary).toContainText("10 events · about 12 s");
  await page.getByTestId("export-pace").selectOption("2.4");
  await expect(summary).toContainText("about 24 s");
  await page.getByTestId("export-start").fill("999");
  await expect(summary).toContainText("valid range");
  await expect(page.getByTestId("export-start-button")).toBeDisabled();
  // Typing in the dialog must not move the viewer's playback.
  await page.getByTestId("export-start").press("ArrowRight");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("the dialog starts from the current view and event", async ({ page }) => {
  await open(page, "thread-pool");
  await page.getByTestId("mode-code").click();
  await page.getByTestId("open-export").click();
  await expect(page.getByRole("radio", { name: "Animation + code" })).toBeChecked();
  await page.getByRole("button", { name: /From event 1/ }).click();
  await expect(page.getByTestId("export-start")).toHaveValue("1");
});

test("exporting PNG frames renders and downloads a zip", async ({ page, request }) => {
  const caps = (await (await request.get("/api/session")).json()).export;
  test.skip(!caps.browser, "no Chrome-family browser installed");
  test.setTimeout(90_000);
  await open(page, "thread-pool");
  await page.getByTestId("open-export").click();
  await page.getByRole("radio", { name: /PNG frames/ }).check();
  await page.getByTestId("export-start").fill("2");
  await page.getByTestId("export-end").fill("3");
  await page.getByTestId("export-smooth").uncheck();
  await page.getByTestId("export-start-button").click();
  await expect(page.getByTestId("export-done")).toBeVisible({ timeout: 60_000 });
  const download = page.waitForEvent("download");
  await page.getByTestId("export-download").click();
  expect((await download).suggestedFilename()).toMatch(/\.zip$/);
});
