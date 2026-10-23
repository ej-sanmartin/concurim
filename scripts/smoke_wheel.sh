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
SAMPLE="$($VENV/bin/python -c 'from concurim.samples import sample_file;print(sample_file("threaded_pipeline.py"))')"
"$CZ" record -o rec.concurim "$SAMPLE" 2>&1 | tail -3
"$CZ" inspect rec.concurim | head -5
# Home screen: examples, then plan + confirm + record a program.
kill $PID 2>/dev/null || true
"$CZ" --no-browser --port 8778 >home.log 2>&1 &
PID=$!
for _ in $(seq 1 50); do
  curl -sf http://127.0.0.1:8778/api/session -o session.json && break
  sleep 0.2
done
"$VENV/bin/python" - <<'PY'
import base64, json, re, time, urllib.request as u

base = "http://127.0.0.1:8778/"
page = u.urlopen(base).read().decode()
token = re.search(r'name="concurim-token" content="([^"]+)"', page).group(1)


def call(path, body=None):
    data = json.dumps(body).encode()
    req = u.Request(base + path, data=data, method="POST")
    req.add_header("X-Concurim-Token", token)
    req.add_header("Content-Type", "application/json")
    return json.load(u.urlopen(req))


assert json.load(u.urlopen(base + "api/session"))["has_trace"] is False
code = "import threading\nthreading.Thread(target=print, args=('hi',)).start()\n"
ws = call("api/workspaces", {"files": [
    {"path": "main.py", "data": base64.b64encode(code.encode()).decode()}]})
plan = call("api/runs/plan", {"workspace_id": ws["id"], "entry": "main.py",
                              "auto": "threads"})
call(f"api/runs/{plan['id']}/start", {})
for _ in range(100):
    st = json.load(u.urlopen(base + f"api/runs/{plan['id']}"))
    if st["state"] != "running":
        break
    time.sleep(0.2)
assert st["state"] == "finished", st
assert st["trace_ready"] is True, st
assert json.load(u.urlopen(base + "api/session"))["has_trace"] is True
print("run via home screen ok")
PY
echo "wheel smoke test passed"
