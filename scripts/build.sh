#!/usr/bin/env bash
# Build the viewer, then the wheel and sdist. Node.js is needed only here,
# never at install or run time: compiled assets ship inside the package.
set -euo pipefail
cd "$(dirname "$0")/.."
(cd frontend && npm ci && npm run build)
rm -rf dist
uv build
