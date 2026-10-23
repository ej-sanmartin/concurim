#!/usr/bin/env bash
# Install the built wheel into a clean venv and exercise the CLI + viewer.
set -euo pipefail
cd "$(dirname "$0")/.."
WHEEL=$(ls dist/*.whl | head -1)
VENV=$(mktemp -d)/venv
WORK=$(mktemp -d)
uv venv --python "${PYTHON:-3.13}" "$VENV" >/dev/null
uv pip install --python "$VENV/bin/python" "$WHEEL" >/dev/null
CZ="$VENV/bin/concurim"
cd "$WORK"   # away from the source tree: only the installed package exists
"$CZ" --version
"$CZ" --help >/dev/null
"$CZ" demo --no-browser --port 8777 >demo.log 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do
  curl -sf http://127.0.0.1:8777/api/replay -o replay.json && break
  sleep 0.2
done
"$VENV/bin/python" - <<'PY'
import json
d = json.load(open("replay.json"))
assert d["summary"]["event_count"] > 50, d["summary"]
assert d["source_paths"] == ["threaded_pipeline.py"], d["source_paths"]
assert d["warnings"] == [], d["warnings"]
print("replay ok:", d["summary"]["event_count"], "events")
PY
curl -sf http://127.0.0.1:8777/ | grep -q "<div id=\"root\">"
ASSET=$(curl -sf http://127.0.0.1:8777/ | grep -o 'assets/[^"]*\.js' | head -1)
curl -sf "http://127.0.0.1:8777/$ASSET" -o /dev/null
curl -sf "http://127.0.0.1:8777/api/source?path=threaded_pipeline.py" | grep -q "def producer"
"$CZ" record -o rec.concurim "$($VENV/bin/python -c 'import concurim.examples as e;print(e.example_path("threaded_pipeline.py"))')" 2>&1 | tail -3
"$CZ" inspect rec.concurim | head -5
echo "wheel smoke test passed"
