import { defineConfig } from "@playwright/test";

// Two real servers: the demo (a recording is already loaded, port 8799) and
// the plain home screen (nothing loaded, port 8798).
const server = (port: number, args: string, path: string) => ({
  command: `uv run concurim ${args} --no-browser --port ${port}`,
  cwd: "..",
  url: `http://127.0.0.1:${port}${path}`,
  reuseExistingServer: !process.env.CI,
  timeout: 60_000,
});

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:8799", viewport: { width: 1440, height: 900 } },
  webServer: [server(8799, "demo", "/api/replay"), server(8798, "", "/api/session")],
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.02 } },
});
