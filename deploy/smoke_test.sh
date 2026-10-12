#!/usr/bin/env bash
# Post-deploy smoke test: is the service up, and can the backend drive it?
#   export VOICE_SERVICE_URL=https://voice.your-domain
#   export VOICE_SERVICE_API_KEY=....
#   bash deploy/smoke_test.sh
set -euo pipefail

BASE="${VOICE_SERVICE_URL:-http://localhost:8080}"
KEY="${VOICE_SERVICE_API_KEY:-}"
PASS=0; FAIL=0
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

echo "Smoke test → $BASE"

echo "[1] /health"
if curl -fsS "$BASE/health" >/dev/null 2>&1; then ok "health responds"; else bad "health unreachable"; fi

echo "[2] /health/providers"
PROV=$(curl -fsS "$BASE/health/providers" 2>/dev/null || true)
if [ -n "$PROV" ]; then
  echo "      configured: $(echo "$PROV" | jq -c '.configured_providers' 2>/dev/null || echo '?')"
  ok "providers listed"
else bad "providers endpoint failed"; fi

if [ -z "$KEY" ]; then
  echo "[3] skipped session create (VOICE_SERVICE_API_KEY not set)"
else
  echo "[3] create session + token"
  SID=$(curl -fsS -X POST "$BASE/voice/session" -H "X-Voice-Service-Key: $KEY" \
        -H 'Content-Type: application/json' \
        -d '{"student_id":"smoke","language":"ar","topic":"البحث الثنائي"}' 2>/dev/null | jq -r '.session_id' 2>/dev/null || true)
  if [ -n "$SID" ] && [ "$SID" != "null" ]; then
    ok "session $SID created"
    TOK=$(curl -fsS -X POST "$BASE/voice/session/$SID/token" -H "X-Voice-Service-Key: $KEY" 2>/dev/null | jq -r '.token' 2>/dev/null || true)
    if [ -n "$TOK" ] && [ "$TOK" != "null" ]; then ok "token minted (${TOK:0:8}...)"; else bad "token mint failed"; fi
  else
    bad "session create failed (check VOICE_SERVICE_API_KEY / VOICE_AUTH_REQUIRED)"
  fi
fi

echo
echo "Result: $PASS passed, $FAIL failed."
[ "$FAIL" -eq 0 ]
