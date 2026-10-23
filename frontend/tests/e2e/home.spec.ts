import { expect, test, type Page } from "@playwright/test";
import { existsSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

// A server with nothing loaded: the home screen, examples, drop and run.
test.use({ baseURL: "http://127.0.0.1:8798" });

async function goHome(page: Page) {
  await page.goto("/");
  await page.getByTestId("home-screen").or(page.getByTestId("home")).first().waitFor();
  if (await page.getByTestId("home").isVisible()) await page.getByTestId("home").click();
  await expect(page.getByTestId("home-screen")).toBeVisible();
}

const SAMPLES = [
  "producer-consumer", "backpressure", "shutdown", "plain-threads", "plain-queues",
  "lock-contention", "semaphore", "thread-pool", "asyncio-tasks", "asyncio-queue",
];

test("home lists the bundled examples and says which are planned", async ({ page }) => {
  await goHome(page);
  for (const id of SAMPLES) await expect(page.getByTestId(`sample-${id}`)).toBeVisible();
  await expect(page.getByText("Planned, not yet supported")).toContainText("Events and conditions");
  await expect(page.getByTestId("dropzone")).toContainText("watch its concurrency unfold");
});

test("an example can be read before it is opened, and opens without running anything", async ({ page }) => {
  await goHome(page);
  await page.getByTestId("source-backpressure").click();
  await expect(page.getByTestId("sample-code")).toContainText("def producer");
  await page.getByTestId("open-backpressure").click();
  await page.getByTestId("flow").waitFor();
  await expect(page.locator("[data-testid=thread][data-thread=producer]")).toHaveCount(1);
  await expect(page.getByTestId("queue")).toHaveCount(1);
  await page.getByTestId("home").click();
  await expect(page.getByTestId("back-to-recording")).toContainText("Bounded queue backpressure");
});

test("the same program shows more at a higher observability level", async ({ page }) => {
  await goHome(page);
  await page.getByTestId("open-plain-threads").click();
  await page.getByTestId("flow").waitFor();
  await expect(page.getByTestId("thread")).toHaveCount(5);
  await expect(page.getByTestId("queue")).toHaveCount(0);
  await page.getByRole("tab", { name: "Trace" }).click();
  await expect(page.getByTestId("trace-info")).toContainText("Plain queue.Queue contents");
  await page.getByTestId("home").click();
  await page.getByTestId("open-plain-queues").click();
  await page.getByTestId("flow").waitFor();
  await expect(page.getByTestId("thread")).toHaveCount(5);
  await expect(page.getByTestId("queue")).toHaveCount(1);
  await page.getByTestId("next").click();
});

test("dropping a .concurim recording opens it without executing anything", async ({ page }) => {
  await goHome(page);
  const trace = fileURLToPath(
    new URL("../../../src/concurim/samples/shutdown.concurim", import.meta.url));
  await page.getByTestId("file-input").setInputFiles(trace);
  await page.getByTestId("flow").waitFor();
  await expect(page.locator(".top .meta")).toContainText("shutdown.concurim");
});

test("a bad file is explained, not ignored", async ({ page }) => {
  await goHome(page);
  await page.getByTestId("file-input").setInputFiles({
    name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello"),
  });
  await expect(page.getByTestId("home-error")).toContainText("Drop a .py file");
});

test("a dropped program runs only after the plan is reviewed and confirmed", async ({ page }) => {
  const marker = join(mkdtempSync(join(tmpdir(), "cz-e2e-")), "ran.txt");
  const code = [
    "import queue, threading",
    `open(${JSON.stringify(marker)}, "w").write("ran")`,
    "q = queue.Queue()",
    "t = threading.Thread(target=lambda: q.get(), name='waiter')",
    "t.start(); q.put(1); t.join()",
    "print('hello from the program')",
  ].join("\n");
  await goHome(page);
  await page.getByTestId("file-input").setInputFiles({
    name: "main.py", mimeType: "text/x-python", buffer: Buffer.from(code),
  });
  const plan = page.getByTestId("plan");
  await expect(plan).toContainText("main.py");
  await expect(plan).toContainText("Working directory");
  await expect(plan).toContainText("Threads");
  await page.waitForTimeout(500);
  expect(existsSync(marker)).toBe(false); // reviewed, not run
  await page.getByTestId("level-queues").check();
  await expect(plan).toContainText("Threads + queues");
  await page.getByTestId("record").click();
  await page.getByTestId("flow").waitFor({ timeout: 20_000 }); // opened automatically
  expect(existsSync(marker)).toBe(true);
  await expect(page.getByTestId("queue")).toHaveCount(1);
  await expect(page.locator("[data-testid=thread][data-thread=waiter]")).toHaveCount(1);
});

test("a failing program shows its output and keeps the recording available", async ({ page }) => {
  await goHome(page);
  await page.getByTestId("file-input").setInputFiles({
    name: "boom.py", mimeType: "text/x-python",
    buffer: Buffer.from("import threading\nthreading.Thread(target=lambda: 1).start()\nraise ValueError('kaboom')\n"),
  });
  await page.getByTestId("record").click();
  const progress = page.getByTestId("run-progress");
  await expect(progress).toHaveAttribute("data-state", "failed", { timeout: 20_000 });
  await expect(page.getByTestId("run-output")).toContainText("ValueError: kaboom");
  await expect(progress).toContainText("exit code 1");
  await page.getByTestId("open-recording").click();
  await page.getByTestId("flow").waitFor();
});

test("a running program can be cancelled", async ({ page }) => {
  await goHome(page);
  await page.getByTestId("file-input").setInputFiles({
    name: "slow.py", mimeType: "text/x-python",
    buffer: Buffer.from("import time\nprint('started', flush=True)\ntime.sleep(60)\n"),
  });
  await page.getByTestId("record").click();
  await expect(page.getByTestId("run-output")).toContainText("started");
  await page.getByTestId("cancel-run").click();
  await expect(page.getByTestId("run-progress")).toHaveAttribute("data-state", "cancelled", { timeout: 20_000 });
});

test("a project folder offers entry-point selection", async ({ page }) => {
  const dir = mkdtempSync(join(tmpdir(), "cz-proj-"));
  writeFileSync(join(dir, "helper.py"), "VALUE = 3\n");
  writeFileSync(join(dir, "tool.py"), "import helper\nprint(helper.VALUE)\n");
  writeFileSync(join(dir, "main.py"), "import helper, threading\nif __name__ == '__main__':\n    t = threading.Thread(target=print, args=(helper.VALUE * 2,))\n    t.start(); t.join()\n");
  await goHome(page);
  await page.getByTestId("dir-input").setInputFiles(dir);
  await expect(page.getByTestId("entry")).toHaveValue("main.py");
  await page.getByTestId("entry").selectOption("tool.py");
  await expect(page.getByTestId("plan")).toContainText("tool.py");
  await page.getByTestId("entry").selectOption("main.py");
  await page.getByTestId("record").click();
  await page.getByTestId("flow").waitFor({ timeout: 20_000 });
});

test("new examples show locks, semaphores, a thread pool and asyncio tasks", async ({ page }) => {
  await goHome(page);
  await page.getByTestId("open-lock-contention").click();
  await page.getByTestId("flow").waitFor();
  await expect(page.getByTestId("sync")).toHaveCount(1);
  await expect(page.getByTestId("sync")).toContainText("lock");
  await page.getByTestId("home").click();
  await page.getByTestId("open-semaphore").click();
  await page.getByTestId("flow").waitFor();
  await expect(page.getByTestId("sync")).toContainText("permits free");
  await page.getByTestId("home").click();
  await page.getByTestId("open-thread-pool").click();
  await page.getByTestId("flow").waitFor();
  await expect(page.getByTestId("executor")).toContainText("running");
  await page.getByTestId("home").click();
  await page.getByTestId("open-asyncio-tasks").click();
  await page.getByTestId("flow").waitFor();
  await expect(page.getByTestId("thread").filter({ hasText: "task" }).first()).toBeVisible();
});

test("many similar workers can be grouped into one node", async ({ page }) => {
  const code = [
    "import threading",
    "ts = [threading.Thread(target=lambda: None, name=f'w{i}') for i in range(6)]",
    "[t.start() for t in ts]",
    "[t.join() for t in ts]",
  ].join("\n");
  await goHome(page);
  await page.getByTestId("file-input").setInputFiles({
    name: "many.py", mimeType: "text/x-python", buffer: Buffer.from(code),
  });
  await page.getByTestId("record").click();
  await page.getByTestId("flow").waitFor({ timeout: 20_000 });
  const before = await page.getByTestId("thread").count();
  expect(before).toBeGreaterThanOrEqual(6);
  await page.getByTestId("group-toggle").click();
  await expect(page.getByTestId("group")).toHaveCount(1);
  await expect(page.getByTestId("thread")).toHaveCount(0);
  await expect(page.getByTestId("group")).toContainText(`${before} threads`);
  await page.getByTestId("group-toggle").click();
  await expect(page.getByTestId("thread")).toHaveCount(before);
  await page.getByRole("tab", { name: "Log" }).click();
  await expect(page.getByTestId("fold").first()).toContainText("×");
  await page.getByTestId("fold").first().click();
  await expect(page.getByTestId("fold").first()).toHaveAttribute("aria-expanded", "true");
});

test("the lock level records locks and a thread pool from a dropped program", async ({ page }) => {
  const code = [
    "import threading",
    "from concurrent.futures import ThreadPoolExecutor",
    "lock = threading.Lock()",
    "def work(_):",
    "    with lock:",
    "        pass",
    "with ThreadPoolExecutor(max_workers=2) as pool:",
    "    list(pool.map(work, range(3)))",
  ].join("\n");
  await goHome(page);
  await page.getByTestId("file-input").setInputFiles({
    name: "locks.py", mimeType: "text/x-python", buffer: Buffer.from(code),
  });
  await page.getByTestId("level-sync").check();
  await expect(page.getByTestId("plan")).toContainText("locks");
  await page.getByTestId("record").click();
  await page.getByTestId("flow").waitFor({ timeout: 20_000 });
  await expect(page.getByTestId("sync")).toHaveCount(1);
  await expect(page.getByTestId("executor")).toHaveCount(1);
});
