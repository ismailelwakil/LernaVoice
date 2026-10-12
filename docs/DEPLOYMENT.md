# Deployment

## Runtime

* Python 3.12+ (developed and tested on 3.13).
* One ASGI process, **one worker**: voice sessions are stateful and live in the
  process that owns the WebSocket.
* Outbound WSS to the provider APIs; inbound WS from clients. Any proxy in
  front must allow WebSocket upgrades and long-lived connections.

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1 \
        --proxy-headers --timeout-keep-alive 75 --no-access-log
```

## Docker

```bash
docker build -t lerna-voice-ai .
docker run --env-file .env -p 8080:8080 lerna-voice-ai
```

The image runs as a non-root user and ships a `HEALTHCHECK` hitting `/health`.

### One-command deploy (compose)

```bash
cp .env.example .env      # then fill in the keys you have
docker compose up --build -d
docker compose logs -f voice-ai
```

`docker-compose.yml` maps `8080`, injects `.env`, and restarts the service on
crash. Pin `CORS_ORIGINS`, set `VOICE_SERVICE_API_KEY` and `VOICE_AUTH_REQUIRED=true`
before exposing it.

## Voice failover (round 27)

The spoken voice is chosen once per session, but if the active voice fails
*before it has spoken* (outage, auth, quota) the cascade automatically retries the
other configured voices in order — **Azure → Fish Audio → ElevenLabs → Gemini →
Deepgram** — so a student never hears silence because one vendor is down. A voice
that drops *mid-line* surfaces an error instead of restarting, so the line is never
spoken twice. Fish Audio (`FISH_AUDIO_API_KEY`) is the backup speaker behind Azure;
it covers the documented languages `en ar fr sw`. Nothing here changes the backend
contract — failover is entirely inside the voice service.

## Environment

Start from [`.env.example`](../.env.example). The essentials:

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `development` | `production` suppresses stack traces and validation detail |
| `PORT` | `8080` | |
| `LOG_LEVEL` | `INFO` | JSON logs to stdout |
| `CORS_ORIGINS` | `*` | comma-separated; pin it in production |
| `VOICE_SERVICE_API_KEY` | – | shared secret; **set it** in production |
| `VOICE_AUTH_REQUIRED` | `false` | set `true` in production |
| `EXPOSE_DEV_DIAGNOSTICS` | `true` | set `false` in production |
| `VOICE_PROVIDER_MODE` | `auto` | |
| `GEMINI_API_KEY` *or* `GOOGLE_GENAI_USE_VERTEXAI` + `GOOGLE_CLOUD_PROJECT` | – | auto-detected |
| `ELEVENLABS_API_KEY`, `DEEPGRAM_API_KEY` | – | backups |
| `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` | – | primary neural TTS voice (free F0 tier) |
| `FISH_AUDIO_API_KEY` (+ `FISH_AUDIO_MODEL`) | `s2.1-pro-free` | **backup TTS voice** — auto-failover behind Azure |
| `LLM_PRIORITY` | `openrouter,gemini` | lesson "brain" order (winner first, other as fallback) |
| `MONGODB_URI` (+ optional `MONGODB_USERNAME`/`MONGODB_PASSWORD`) | – | unset ⇒ in-memory, non-durable |
| `LERNA_INTEGRATION_MODE` | `auto` | `inprocess` needs `LERNA_AI_SERVICE_PATH` / `ACADEMIC_OS_DATA_DIR` |

## Gemini auth, concretely

**Vertex / Agent Platform**
```
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=my-project
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GEMINI_VERTEX_LIVE_MODEL=gemini-3.8-live
```

**Developer API**
```
GOOGLE_GENAI_USE_VERTEXAI=false
GEMINI_API_KEY=AIza...
GEMINI_LIVE_MODEL=gemini-2.5-flash-native-audio-preview-12-2025
```

A Vertex model id will not work with a Developer API key, and vice versa. The
service picks the model that matches the auth path it detects.

## MongoDB

Collections: `voice_sessions`, `voice_checkpoints`, `voice_interactions`,
`voice_questions`, `voice_provider_events`. Indexes on `session_id`,
`(student_id, updated_at)` and `(student_id, course_id, lesson_id)` are created
on startup. Without `MONGODB_URI` the service runs on the in-memory repository —
fine for demos, **not** for production (state dies with the process).

## Scaling

* Horizontal scale with **sticky sessions** (route by `session_id`); a client
  must reconnect to the worker that owns its session, or create a new session.
* A reconnect to a cold worker rehydrates state from MongoDB, so the lesson
  survives, but the provider socket is re-established.
* Budget ~1 concurrent provider socket per active session; provider rate limits,
  not CPU, are usually the binding constraint.

## Health & monitoring

| Endpoint | Use |
|---|---|
| `GET /health` | liveness/readiness probe (public) |
| `GET /health/providers` | vendor circuit-breaker state, routing plan, capability matrix |

Logs are single-line JSON with `request_id` and `session_id` context and a
redactor that strips keys and connection strings. Useful alerts:
`provider.fallback_started` rate, circuit-breaker opens, `speech_to_first_audio`
p95, `VOICE_PROVIDER_UNAVAILABLE` count.

## Secrets

* Provider keys live only in the service environment. The browser only ever
  receives a 15-minute `vst_*` session token.
* `.env` is git-ignored; `.env.example` contains blank placeholders only.
* Rotate any key that has ever been pasted into a chat, ticket or log.
