import { expect, test, type Page } from "@playwright/test";

const position = (p: Page) => p.getByTestId("position");
const stats = (p: Page) => p.getByTestId("queue-stats");
const title = (p: Page) => p.locator("[data-testid=explanation] h2");

async function stepUntil(p: Page, wanted: string, max = 150) {
  for (let i = 0; i < max; i++) {
    if ((await title(p).innerText()) === wanted) return;
    await p.keyboard.press("ArrowRight");
  }
  throw new Error(`never reached "${wanted}"`);
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByTestId("flow").waitFor();
});

test("shows producers, consumers and the bounded queue from a real recording", async ({ page }) => {
  await expect(page.getByTestId("thread")).toHaveCount(5);
  await expect(page.locator("[data-thread^=producer]")).toHaveCount(2);
  await expect(page.locator("[data-thread^=consumer]")).toHaveCount(2);
  await expect(page.getByTestId("queue")).toHaveCount(1);
  await expect(stats(page)).toContainText("0 / 3 queued");
});

test("stepping forward then backward restores the exact visible state", async ({ page }) => {
  await stepUntil(page, "Item enqueued");
  const snapshot = async () => ({
    stats: await stats(page).textContent(),
    tokens: await page.locator("[data-testid^=token-]:not([data-hidden])").count(),
    pos: await position(page).innerText(),
    text: await page.getByTestId("explanation-text").innerText(),
  });
  for (let k = 0; k < 4; k++) {
    const before = await snapshot();
    await page.getByTestId("next").click();
    await page.getByTestId("prev").click();
    expect(await snapshot()).toEqual(before);
    await page.getByTestId("next").click();
  }
});

test("queue items appear on enqueue and move to the consumer on dequeue", async ({ page }) => {
  await stepUntil(page, "Item enqueued");
  const text = await page.getByTestId("explanation-text").innerText();
  const oid = /object-\d+/.exec(text)![0];
  const token = page.getByTestId(`token-${oid}`);
  await expect(token).toHaveAttribute("data-phase", "queued");
  await stepUntil(page, "Item dequeued");
  const dequeued = /object-\d+/.exec(
    await page.getByTestId("explanation-text").innerText(),
  )![0];
  await expect(page.getByTestId(`token-${dequeued}`)).toHaveAttribute("data-phase", "held");
  // The explanation names the worker that performed the operation.
  await expect(page.getByTestId("explanation-text")).toContainText(/consumer-\d/);
});

test("play advances, pause holds, keyboard controls work", async ({ page }) => {
  await page.keyboard.press("Space");
  await expect.poll(async () => position(page).locator("xpath=..").locator("input").inputValue())
    .not.toBe("1");
  await page.keyboard.press("Space");
  const a = await page.getByTestId("goto").inputValue();
  await page.waitForTimeout(800);
  expect(await page.getByTestId("goto").inputValue()).toBe(a);
  await page.keyboard.press("End");
  const total = (await position(page).innerText()).replace("/ ", "");
  expect(await page.getByTestId("goto").inputValue()).toBe(total);
  await page.keyboard.press("Home");
  expect(await page.getByTestId("goto").inputValue()).toBe("1");
});

test("a blocked producer shows as waiting with an accurate explanation", async ({ page }) => {
  await stepUntil(page, "Put blocked");
  await expect(page.getByTestId("explanation-text")).toContainText("was full (3/3)");
  await expect(page.locator("[data-testid=thread][data-status=waiting]").first()).toBeVisible();
});

test("event source opens code on the line that triggered the event", async ({ page }) => {
  await stepUntil(page, "Item enqueued");
  await page.getByTestId("open-code").click();
  await expect(page.getByTestId("codeview")).toBeVisible();
  const hit = page.locator("[data-testid=code] .line[data-hit]", { hasText: "jobs.put(" });
  await expect(hit).toBeVisible();
});

test("selecting an item shows its journey and history", async ({ page }) => {
  await stepUntil(page, "Item dequeued");
  const text = await page.getByTestId("explanation-text").innerText();
  const oid = /object-\d+/.exec(text)![0];
  await page.getByTestId(`token-${oid}`).click();
  const inspector = page.getByTestId("inspector");
  await expect(inspector).toContainText(oid);
  await expect(inspector).toContainText("Journey");
  await expect(inspector).toContainText("queued @ Jobs");
});

test("clicking the timeline seeks", async ({ page }) => {
  const svg = page.locator("[data-testid=timeline] svg").first();
  const box = (await svg.boundingBox())!;
  await page.mouse.click(box.x + box.width * 0.5, box.y + 10);
  const pos = Number(await page.getByTestId("goto").inputValue());
  const total = Number((await position(page).innerText()).replace("/ ", ""));
  expect(pos).toBeGreaterThan(total * 0.4);
  expect(pos).toBeLessThan(total * 0.6);
});

test("trace tab discloses what is not observed", async ({ page }) => {
  await page.getByRole("tab", { name: "Trace" }).click();
  await expect(page.getByTestId("trace-info")).toContainText("Not observed");
  await expect(page.getByTestId("trace-info")).toContainText("GIL");
});

test("renders untrusted strings as text, not HTML", async ({ page }) => {
  await page.route("**/api/replay", async (route) => {
    const res = await route.fetch();
    const data = await res.json();
    const t = Object.values<any>(data.entities.threads)[0];
    t.name = "<img src=x onerror=window.__xss=1>";
    data.frames.forEach((f: any) => {
      Object.values<any>(f.changes.threads ?? {}).forEach((s) => {
        if (s.id === t.id) s.name = t.name;
      });
    });
    await route.fulfill({ json: data });
  });
  await page.reload();
  await page.getByTestId("flow").waitFor();
  expect(await page.evaluate(() => (window as any).__xss)).toBeUndefined();
  await expect(page.getByText("<img src=x onerror=window.__xss=1>").first()).toBeVisible();
});
