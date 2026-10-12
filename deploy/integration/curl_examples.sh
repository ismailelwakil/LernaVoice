#!/usr/bin/env bash
# The whole integration flow with curl. Requires: curl, jq.
#   export VOICE_SERVICE_URL=http://localhost:8080
#   export VOICE_SERVICE_API_KEY=....
#   bash deploy/integration/curl_examples.sh
set -euo pipefail

BASE="${VOICE_SERVICE_URL:-http://localhost:8080}"
KEY="${VOICE_SERVICE_API_KEY:?set VOICE_SERVICE_API_KEY}"
H_KEY="X-Voice-Service-Key: $KEY"

echo "== 0) health / configured providers =="
curl -fsS "$BASE/health" | jq '{status}'
curl -fsS "$BASE/health/providers" | jq '{configured_providers, routing: .routing.priority}'

echo "== 1) create a session (Arabic lesson) =="
SESSION=$(curl -fsS -X POST "$BASE/voice/session" \
  -H "$H_KEY" -H 'Content-Type: application/json' \
  -d '{"student_id":"student-123","language":"ar","topic":"البحث الثنائي","level":"beginner"}')
echo "$SESSION" | jq '{session_id, language, websocket_url}'
SID=$(echo "$SESSION" | jq -r '.session_id')

echo "== 2) mint a browser token (15-min TTL) =="
TOKEN=$(curl -fsS -X POST "$BASE/voice/session/$SID/token" -H "$H_KEY" | jq -r '.token')
echo "token: ${TOKEN:0:12}... (expires in 900s)"

echo "== 3) the URL the browser opens =="
WS=$(echo "$SESSION" | jq -r '.websocket_url')
echo "$WS?token=$TOKEN"
echo "   client sends binary PCM16 16 kHz mono; receives JSON events."

echo "== optional) upload material, then teach from it =="
DOC=$(curl -fsS -X POST "$BASE/voice/material" \
  -H "$H_KEY" -H 'Content-Type: application/json' \
  -d '{"title":"Quantum Tunnelling","text":"...paste the student material...","language":"en"}' | jq -r '.document_id')
echo "document_id: $DOC   (pass it as document_ids when creating the session)"
