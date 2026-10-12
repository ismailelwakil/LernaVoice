# LERNA Voice AI — Deploy & Backend Integration

Everything the LERNA backend team needs to **deploy** this service and **integrate**
it. The voice service is standalone; your backend only creates sessions and mints
tokens — it never proxies audio.

```
deploy/
├── README.md                  ← you are here
├── docker-compose.yml         ← one-command production deploy (builds the repo root)
├── .env.production.example    ← the variables to set in production (copy → .env)
├── nginx.conf.example         ← reverse proxy that allows WebSocket upgrades
├── smoke_test.sh              ← post-deploy check: health + create session + token
├── integration/
│   ├── backend_client.py      ← Python: create session → mint token → ws_url
│   ├── backend_client.ts      ← TypeScript/Node (fetch) version
│   └── curl_examples.sh       ← the same flow with curl + jq
└── docs/
    ├── DEPLOYMENT.md          ← runtime, Docker, env, voice failover
    ├── BACKEND_HANDOFF.md     ← the full integration contract & sequence
    ├── API.md                 ← every HTTP endpoint
    └── WEBSOCKET_PROTOCOL.md  ← the WS frames (binary audio ⇄ JSON events)
```

---

## 1. Deploy (Docker)

```bash
# from the repo root (the folder that contains app/ and Dockerfile)
cp deploy/.env.production.example .env      # then fill in the keys you have
docker compose -f deploy/docker-compose.yml up --build -d
docker compose -f deploy/docker-compose.yml logs -f voice-ai
```

The service listens on **8080**. One worker only — voice sessions are stateful and
live in the process that owns the WebSocket. Scale horizontally behind a
sticky-session load balancer, never with extra workers.

Put `nginx.conf.example` in front of it (it forwards the WS upgrade and keeps
connections alive long enough for a lesson).

## 1b. Deploy on Railway (managed PaaS)

The image is Railway-ready out of the box:

* **Build:** Railway builds from the `Dockerfile` at the repo root.
  * Files pushed with `voice-ai/` **as the repo root** → nothing to configure.
  * Files pushed **inside a sub-folder** (e.g. `voice-ai/Dockerfile`) → set the
    service variable `RAILWAY_DOCKERFILE_PATH=voice-ai/Dockerfile`, otherwise the
    build fails with "Dockerfile not found".
* **Port:** do **not** hardcode one. Railway injects `PORT`; the container CMD is
  `uvicorn … --port ${PORT}`, so it binds automatically, on `0.0.0.0` (required by
  Railway's proxy).
* **Healthcheck:** set the path to `/health` (Settings → Deploy → Healthcheck Path).
  The image also declares its own `HEALTHCHECK`.
* **WebSockets** (the live audio socket) are supported on the same port — no extra
  service or flag needed.
* **Variables** to add in Railway → *Variables*: `VOICE_SERVICE_API_KEY`,
  `OPENROUTER_API_KEY` and/or `GEMINI_API_KEY`, `AZURE_SPEECH_KEY` +
  `AZURE_SPEECH_REGION=germanywestcentral`, `FISH_AUDIO_API_KEY`, `MONGODB_URI`.
  (All optional: with none set the service still boots and runs in open/mock mode.)
* **Replicas:** run **one** replica per deployment (voice sessions are in-process).
  Use sticky sessions if you scale out.

```bash
# the exact command Railway runs at start:
#   uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers
```

Verification after deploy:

```bash
curl -fsS "$RAILWAY_PUBLIC_DOMAIN/health"
curl -fsS "$RAILWAY_PUBLIC_DOMAIN/health/providers"
```

## 2. Configure (the only required secret)

| Variable | Why |
|---|---|
| `VOICE_SERVICE_API_KEY` | **Shared secret your backend sends on every call.** Set a long random value. |
| `VOICE_AUTH_REQUIRED=true` | Enforce the key in production. |
| `CORS_ORIGINS` | Pin to your web origin(s). |
| `EXPOSE_DEV_DIAGNOSTICS=false` | Hide stack traces. |
| Provider keys | `OPENROUTER_API_KEY` (brain), `GEMINI_API_KEY` (fallback brain), `AZURE_SPEECH_KEY`+`AZURE_SPEECH_REGION` (voice), `FISH_AUDIO_API_KEY` (backup voice), `MONGODB_URI` (persistence). All optional — it runs offline without them. |

## 3. Integrate (three calls)

All HTTP calls carry the header **`X-Voice-Service-Key: <VOICE_SERVICE_API_KEY>`**.
The key must stay server-side — it never reaches the browser.

```
1) POST /voice/session                 → 201 { session_id, websocket_url, ... }
   body: { student_id, language, topic_id?, topic?, level?, document_ids?, resume_latest? }

2) POST /voice/session/{id}/token      → { token: "vst_...", expires_in: 900, ... }

3) hand the browser:  {websocket_url}?token={token}
   WS /voice/session/{id}/audio?token=vst_...
   client sends binary PCM16 16 kHz mono, receives JSON events
```

Tokens are single-session and expire in **15 minutes** — mint a fresh one per
connection attempt. See `integration/` for ready-to-copy code and `docs/API.md`
for every field.

### Offer continuation (resume, not restart)
Before creating a session, call `GET /voice/students/{student_id}/latest`. If a
session exists for the same lesson, create the next one with `resume_latest: true`
so the student gets a recap instead of starting over.

## 4. Verify

```bash
VOICE_SERVICE_URL=https://voice.your-domain VOICE_SERVICE_API_KEY=... bash deploy/smoke_test.sh
```

It checks `/health`, lists configured providers, creates a session, mints a token,
and prints the WebSocket URL the browser should open.

## 5. What is wired (so you know what to expect)
- **Brain:** OpenRouter primary, Gemini fallback (`LLM_PRIORITY=openrouter,gemini`).
- **Voice:** Azure primary; **Fish Audio fails over automatically** if Azure breaks
  before speaking (Azure → Fish → ElevenLabs → Gemini → Deepgram). Failover is
  internal — your integration does not change.
- **Languages:** 10 (ar, am, en, fr, ha, ig, so, sw, yo, zu). `GET /voice/languages`
  reports exactly what each can route to.
- **Conversation policy:** unclear speech → asks to repeat (×3) → asks to type →
  "I didn't get your point"; impolite → one warning → ends the lesson on the second.
- **Lessons from uploads:** `POST /voice/material` ingests a student's material and
  returns a `document_id`; pass it in `document_ids` when creating the session.
