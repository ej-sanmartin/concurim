import { expect, test, type Locator, type Page } from "@playwright/test";

// The demo server: a real recording of the threaded pipeline is loaded.
const title = (p: Page) => p.locator("[data-testid=explanation] h2");
const goto = (p: Page) => p.getByTestId("goto");

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  // Clear once per tab, so a reload can prove persistence.
  await page.addInitScript(() => {
    if (sessionStorage.getItem("fresh")) return;
    sessionStorage.setItem("fresh", "1");
    localStorage.clear();
  });
  await page.goto("/");
  await page.getByTestId("flow").waitFor();
});

async function center(l: Locator) {
  const b = (await l.boundingBox())!;
  return { x: b.x + b.width / 2, y: b.y + b.height / 2, w: b.width };
}

/** Position of ``node`` relative to the queue, in queue-widths (zoom-free). */
async function relative(page: Page, node: Locator) {
  const q = await center(page.getByTestId("queue"));
  const n = await center(node);
  return { x: (n.x - q.x) / q.w, y: (n.y - q.y) / q.w };
}

async function drag(page: Page, node: Locator, dx: number, dy: number) {
  const c = await center(node);
  await page.mouse.move(c.x, c.y);
  await page.mouse.down();
  await page.mouse.move(c.x + dx / 2, c.y + dy / 2, { steps: 5 });
  await page.mouse.move(c.x + dx, c.y + dy, { steps: 5 });
  await page.mouse.up();
}

test("nodes can be dragged, the layout is remembered, and it can be reset", async ({ page }) => {
  const node = page.locator("[data-testid=thread][data-thread=producer-1]");
  const before = await relative(page, node);
  await drag(page, node, -90, 110);
  const moved = await relative(page, node);
  expect(Math.abs(moved.y - before.y)).toBeGreaterThan(0.2);

  await page.reload();
  await page.getByTestId("flow").waitFor();
  await page.waitForTimeout(500); // let the initial fit settle
  const kept = await relative(page, node);
  expect(kept.x).toBeCloseTo(moved.x, 1);
  expect(kept.y).toBeCloseTo(moved.y, 1);

  await page.getByTestId("reset-layout").click();
  await page.waitForTimeout(500);
  const reset = await relative(page, node);
  expect(reset.x).toBeCloseTo(before.x, 1);
  expect(reset.y).toBeCloseTo(before.y, 1);
});

test("dragging a node does not change the recorded state or position", async ({ page }) => {
  await goto(page).fill("30");
  const pos = await goto(page).inputValue();
  const text = await page.getByTestId("explanation-text").innerText();
  await drag(page, page.locator("[data-testid=thread][data-thread=consumer-1]"), 60, -60);
  expect(await goto(page).inputValue()).toBe(pos);
  expect(await page.getByTestId("explanation-text").innerText()).toBe(text);
});

test("tokens follow a dragged node", async ({ page }) => {
  // Find an event where a producer is holding an item in hand.
  for (let i = 0; i < 80; i++) {
    if ((await page.locator("[data-testid^=token-][data-phase=putting]").count()) > 0) break;
    await page.getByTestId("next").click();
  }
  const token = page.locator("[data-testid^=token-][data-phase=putting]").first();
  const before = await center(token);
  // The holder is the thread drawn nearest to the token.
  const threads = page.locator("[data-testid=thread]");
  let holder = threads.first();
  let best = Infinity;
  for (let i = 0; i < (await threads.count()); i++) {
    const c = await center(threads.nth(i));
    const d = Math.hypot(c.x - before.x, c.y - before.y);
    if (d < best) { best = d; holder = threads.nth(i); }
  }
  await drag(page, holder, 0, 70);
  await page.waitForTimeout(100);
  const after = await center(token);
  expect(after.y - before.y).toBeGreaterThan(40);
});

test("categories can be hidden and shown", async ({ page }) => {
  await expect(page.getByTestId("thread")).toHaveCount(5);
  await page.getByTestId("show-consumer").uncheck();
  await expect(page.getByTestId("thread")).toHaveCount(3);
  await page.getByTestId("show-queue").uncheck();
  await expect(page.getByTestId("queue")).toHaveCount(0);
  await page.getByTestId("show-consumer").check();
  await page.getByTestId("show-queue").check();
  await expect(page.getByTestId("thread")).toHaveCount(5);
  await expect(page.getByTestId("queue")).toHaveCount(1);
});

test("focus selection needs a selection; fit works", async ({ page }) => {
  await expect(page.getByTestId("focus")).toBeDisabled();
  await page.locator("[data-testid=thread][data-thread=consumer-2]").click();
  await expect(page.getByTestId("focus")).toBeEnabled();
  const before = await center(page.getByTestId("queue"));
  await page.getByTestId("focus").click();
  await page.waitForTimeout(500);
  const after = await center(page.locator("[data-testid=thread][data-thread=consumer-2]"));
  const box = page.getByTestId("flow");
  const area = (await box.boundingBox())!;
  expect(Math.abs(after.x - (area.x + area.width / 2))).toBeLessThan(area.width * 0.2);
  await page.getByTestId("fit").click();
  await page.waitForTimeout(500);
  const fitted = await center(page.getByTestId("queue"));
  expect(Math.abs(fitted.x - before.x)).toBeLessThan(40);
});

test("Animation and Timeline are two views of the same position", async ({ page }) => {
  await goto(page).fill("37");
  await page.getByTestId("mode-timeline").click();
  await expect(page.locator(".timeline.full")).toBeVisible();
  await expect(page.getByTestId("flow")).toHaveCount(0);
  expect(await goto(page).inputValue()).toBe("37");
  const svg = page.locator(".timeline.full svg").first();
  const box = (await svg.boundingBox())!;
  await page.mouse.click(box.x + box.width * 0.75, box.y + 12);
  const picked = await goto(page).inputValue();
  expect(Number(picked)).toBeGreaterThan(70);
  await page.getByTestId("show-in-animation").click();
  await page.getByTestId("flow").waitFor();
  expect(await goto(page).inputValue()).toBe(picked);
  // The choice is remembered.
  await page.getByTestId("mode-timeline").click();
  await page.reload();
  await expect(page.locator(".timeline.full")).toBeVisible();
});

test("jump to the next blocking event, and to the next event of a selection", async ({ page }) => {
  await page.getByTestId("next-blocking").click();
  await expect(title(page)).toHaveText(/(Put|Get) blocked/);
  const first = Number(await goto(page).inputValue());
  await page.getByTestId("next-blocking").click();
  expect(Number(await goto(page).inputValue())).toBeGreaterThan(first);
  await page.keyboard.press("Shift+B");
  expect(Number(await goto(page).inputValue())).toBe(first);

  await page.keyboard.press("Home");
  await page.locator("[data-testid=thread][data-thread=consumer-1]").click();
  await page.getByTestId("next-selected").click();
  const a = Number(await goto(page).inputValue());
  await page.keyboard.press("n");
  expect(Number(await goto(page).inputValue())).toBeGreaterThan(a);
  await expect(page.getByTestId("explanation-text")).toContainText("consumer-1");
});

test("real-time pace plays through the recording and idle gaps can be compressed", async ({ page }) => {
  await page.getByTestId("pace").selectOption("realtime");
  await expect(page.getByTestId("compress")).toBeChecked();
  await page.getByTestId("speed").selectOption("8");
  await page.getByTestId("play").click();
  await expect.poll(async () => Number(await goto(page).inputValue()), { timeout: 8000 })
    .toBeGreaterThan(30);
  await page.getByTestId("play").click();
});
