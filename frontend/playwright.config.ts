import { defineConfig } from "@playwright/test";

// The webServer records the bundled example for real and serves it.
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:8799", viewport: { width: 1440, height: 900 } },
  webServer: {
    command: "uv run concurim demo --no-browser --port 8799",
    cwd: "..",
    url: "http://127.0.0.1:8799/api/replay",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.02 } },
});
