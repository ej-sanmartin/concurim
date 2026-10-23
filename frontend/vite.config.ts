import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// The production build lands inside the Python package so the wheel can
// serve it without Node.js. In dev, run `concurim view --port 8765 <trace>`.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: fileURLToPath(
      new URL("../src/concurim/viewer/static", import.meta.url),
    ),
    emptyOutDir: true,
    sourcemap: false,
  },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  test: { include: ["src/**/*.test.ts"] },
});
