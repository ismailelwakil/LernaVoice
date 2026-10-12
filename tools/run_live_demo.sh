#!/usr/bin/env bash
# Start the service on the REAL vendors (Vertex Gemini Live). Requires .env.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "no .env — copy .env.example and fill it in"; exit 2
fi
if grep -q '^GOOGLE_APPLICATION_CREDENTIALS=' .env; then
  cred=$(grep '^GOOGLE_APPLICATION_CREDENTIALS=' .env | cut -d= -f2-)
  if [ -n "$cred" ] && [ ! -f "$cred" ]; then
    echo "credential file not found: $cred"
    echo "drop the service-account JSON there, or fix the path in .env"; exit 2
  fi
fi

# No VOICE_ENABLE_MOCK_PROVIDERS here on purpose: that switch is what makes the service
# serve synthetic audio instead of the vendor's own voice.
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${VOICE_API_PORT:-3000}"
