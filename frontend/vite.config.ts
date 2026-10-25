import { copyFileSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vitest/config";
import react from "@vitejs/plugin-react";

const LOGO = fileURLToPath(
  new URL("../docs/images/logo.png", import.meta.url),
);
const LOGO_OUT = fileURLToPath(
  new URL("../src/concurim/viewer/static/logo.png", import.meta.url),
);

/** Ship docs/images/logo.png as the viewer favicon, including in dev. */
function logoFavicon(): Plugin {
  return {
    name: "logo-favicon",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url?.split("?")[0] !== "/logo.png") return next();
        res.setHeader("Content-Type", "image/png");
        res.end(readFileSync(LOGO));
      });
    },
    closeBundle() {
      copyFileSync(LOGO, LOGO_OUT);
    },
  };
}

// The production build lands inside the Python package so the wheel can
// serve it without Node.js. In dev, run `concurim view --port 8765 <trace>`.
export default defineConfig({
  plugins: [react(), logoFavicon()],
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
