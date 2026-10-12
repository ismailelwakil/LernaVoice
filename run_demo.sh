#!/usr/bin/env bash
# One-command launcher for the LERNA Voice AI demo.
#
#   bash run_demo.sh            # start API (:3000) + voice-mode UI (:8501)
#   bash run_demo.sh install    # only (re)install dependencies
#
# Runs in offline demo mode: mock providers rebound to the real vendor names,
# so the router / cascade / failover / WebSocket paths are the real code with
# synthetic audio. No API keys required. LERNA integration is disabled so the
# service is fully standalone.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PY="${PYTHON:-python3}"
API_PORT="${VOICE_API_PORT:-3000}"
UI_PORT="${VOICE_UI_PORT:-8501}"

install_deps() {
  echo "==> installing dependencies"
  "$PY" -m pip install -q --disable-pip-version-check \
    fastapi "uvicorn[standard]" pydantic pydantic-settings \
    python-dotenv websockets httpx streamlit
  "$PY" -c "import app.main, streamlit" && echo "    ok"
}

if [[ "${1:-}" == "install" ]]; then
  install_deps
  exit 0
fi

"$PY" -c "import fastapi" 2>/dev/null || install_deps

pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "streamlit run streamlit_app/app.py" 2>/dev/null || true
sleep 1

echo "==> API + dev console  ->  http://0.0.0.0:${API_PORT}"
VOICE_ENABLE_MOCK_PROVIDERS=true \
LERNA_INTEGRATION_MODE=disabled \
nohup "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT" \
  > /tmp/voice-api.log 2>&1 &

echo "==> voice-mode UI      ->  http://0.0.0.0:${UI_PORT}"
VOICE_SERVICE_PORT="$API_PORT" \
nohup "$PY" -m streamlit run streamlit_app/app.py \
  --server.port "$UI_PORT" --server.address 0.0.0.0 --server.headless true \
  > /tmp/voice-ui.log 2>&1 &

sleep 5
for p in "$API_PORT" "$UI_PORT"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${p}/" || true)
  echo "    localhost:${p} -> ${code:-down}"
done
echo "==> logs: /tmp/voice-api.log  /tmp/voice-ui.log"
