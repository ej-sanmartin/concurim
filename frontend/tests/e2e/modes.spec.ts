import { expect, test, type Page } from "@playwright/test";

// Fullscreen and code modes, on real recordings (home server: samples).
test.use({ baseURL: "http://127.0.0.1:8798" });

async function open(page: Page, sample: string) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByTestId("home-screen").or(page.getByTestId("home")).first().waitFor();
  if (await page.getByTestId("home").isVisible()) await page.getByTestId("home").click();
  await page.getByTestId(`open-${sample}`).click();
  await page.getByTestId("flow").waitFor();
}

test("fullscreen keeps the transport bar and is easy to leave", async ({ page }) => {
  await open(page, "thread-pool");
  const fs = page.locator(".app[data-fullscreen]");
  await expect(page.locator(".top")).toBeVisible();
  await page.getByTestId("fullscreen").click();
  await expect(fs).toHaveCount(1);
  await expect(page.locator(".top")).toBeHidden();
  await expect(page.getByTestId("play")).toBeVisible();
  await expect(page.getByLabel("Seek to event")).toBeVisible();
  await expect(page.locator(".caption").getByTestId("explanation")).toBeVisible();
  await page.getByTestId("next").click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: "/tmp/cz-fullscreen.png" });
  await page.getByTestId("exit-fullscreen").click();
  await expect(fs).toHaveCount(0);
  await expect(page.locator(".top")).toBeVisible();
  await page.keyboard.press("z");
  await expect(fs).toHaveCount(1);
  await page.keyboard.press("z");
  await expect(fs).toHaveCount(0);
});

test("code mode marks each busy worker's line", async ({ page }) => {
  await open(page, "thread-pool");
  await page.getByTestId("mode-code").click();
  await expect(page.getByTestId("codeview")).toBeVisible();
  await expect(page.getByTestId("flow")).toBeVisible();
  const marks = page.getByTestId("code-mark");
  for (let i = 0; i < 300 && (await marks.count()) < 2; i++) {
    await page.getByTestId("next").click();
  }
  expect(await marks.count()).toBeGreaterThan(1);
  // A task that was just started has no known line yet: its body is shaded.
  const body = page.locator("[data-testid=code] .line[data-shade~=body]");
  expect(await body.count()).toBeGreaterThan(1);
  await page.waitForTimeout(400);
  await page.screenshot({ path: "/tmp/cz-code.png" });
});

test("process pools open with workers drawn as processes", async ({ page }) => {
  await open(page, "process-pool");
  await expect(page.getByTestId("executor")).toHaveCount(1);
  await page.getByLabel("End", { exact: true }).click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: "/tmp/cz-process.png" });
  // Worker processes show up in code mode too, on the task's function.
  await page.getByTestId("mode-code").click();
  await page.getByLabel("Beginning").click();
  const marks = page.getByTestId("code-mark");
  for (let i = 0; i < 40 && (await marks.count()) < 3; i++) {
    await page.getByTestId("next").click();
  }
  expect(await marks.count()).toBeGreaterThan(1);
  await page.waitForTimeout(400);
  await page.screenshot({ path: "/tmp/cz-process-code.png" });
});
