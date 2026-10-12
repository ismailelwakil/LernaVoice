# REST API

Base URL: `http://<host>:8080`. All payloads are JSON. Interactive schema at
`/docs` (disabled when `APP_ENV=production` if you choose to turn it off).

## Authentication

Service-to-service: send the shared secret on every call.

```
X-Voice-Service-Key: <VOICE_SERVICE_API_KEY>
# or
Authorization: Bearer <VOICE_SERVICE_API_KEY>
```

Browser clients must **never** hold that key. The LERNA backend creates the
session, then calls `POST /voice/session/{id}/token` and hands the resulting
short-lived `vst_*` token (15 min, single session) to the browser for the
WebSocket upgrade only.

When `VOICE_AUTH_REQUIRED=false` and no key is configured (local dev), auth is
skipped. `/health` is always public.

## Endpoints

### `POST /voice/session` → `201`
Create a session.

```json
{
  "student_id": "student-001",
  "language": "ar",
  "dialect": "ar-MSA",
  "topic_id": "binary-search",
  "topic": "Binary Search",
  "course_id": "algorithms-101",
  "lesson_id": "lesson-binary-search",
  "level": "beginner",
  "document_ids": ["doc_12"],
  "resume_latest": false
}
```

`level` is `beginner` | `intermediate` | `advanced` (aliases such as `b1` or
`first year` are accepted). Leave it out and the level comes from the student's
LERNA profile, then the local mirror, then `intermediate`; an unknown level is a
`422`. The level changes how the explanation is pitched — never what the lesson
is, so checkpoints, concepts and resume are unaffected. See
`docs/EXPLANATIONS.md`.

`topic_id` comes from `GET /curriculum/courses` and is preferred: it brings the
course id, lesson id and the section-by-section lesson plan with it. A free-text
`topic` is still accepted and is matched against the catalogue when possible
(`"merge sort"` → `merge-sort`); an unmatched topic simply runs without a plan.
See `CURRICULUM.md`.

Response (`SessionSummary`):

```json
{
  "session_id": "vs_6b3f...",
  "student_id": "student-001",
  "language": "ar",
  "state": "idle",
  "current_topic": "Binary Search",
  "active_pipeline": {"mode": "realtime", "realtime": "gemini"},
  "websocket_url": "ws://host:8080/voice/session/vs_6b3f.../audio",
  "is_returning": false
}
```

`resume_latest: true` forks the student's most recent session for this lesson:
a **new** session id that inherits topic, concepts covered, checkpoint and
unresolved questions, with `previous_session_id` set. Starting it emits
`session.recap`.

### `GET /voice/session/{id}`
Same `SessionSummary`. `404` with `VOICE_SESSION_NOT_FOUND` if unknown.

### `GET /voice/session/{id}/state`
Full state for a client or dev panel: language, state, topic/section,
`topic_id`, `lesson_plan` (the ordered steps being taught),
`concepts_covered`, `student_questions`, `interrupt_count`, `resume_count`,
`is_returning`, `previous_session_id`, `checkpoint`, `provider_history`, and a
`diagnostics` block (`active_provider`, `fallback_reason`, `retry_count`,
`failover_count`, `latency`). Diagnostics are suppressed when
`EXPOSE_DEV_DIAGNOSTICS=false`.

### `GET /voice/session/{id}/history`
Persisted records: checkpoints, interactions, questions, provider events.

### `POST /voice/session/{id}/token`
`{"token": "vst_...", "expires_in": 900}`

### `POST /voice/session/{id}/start?recap=`
Connects a provider and begins the lesson. Omit `recap` to let the server decide.

### `POST /voice/session/{id}/interrupt`
```json
{
  "interrupted": true,
  "playback_stop_ms": 12,
  "acknowledgement": "طبعًا، اتفضل اسأل سؤالك.",
  "checkpoint": { "checkpoint_id": "cp_...", "topic": "...", "section": "...",
                  "concepts_covered": ["..."], "next_step": "...",
                  "resume_instruction": "..." }
}
```

### `POST /voice/session/{id}/question`
`{"text": "ليه بنقسم المصفوفة على اتنين؟"}` →
`{"question_id": "...", "is_followup": false, "rag_used": true, "sources": [...]}`
Interrupts first if the tutor is speaking.

### `POST /voice/session/{id}/resume`
Continues from the checkpoint. Never restarts the lesson.

### `POST /voice/session/{id}/language`
`{"language": "sw"}` → re-plans the pipeline, keeps every piece of learning state.
Arabic is one language and one register: `{"language": "ar"}` (or the older
`{"language": "ar-MSA"}` / `{"dialect": "egyptian"}` spellings, which normalise to
`ar-MSA`) gives the formal voice and the formal phrase set without touching the
lesson. `dialect` is ignored for the other nine languages.

### `POST /voice/session/{id}/pause` · `POST /voice/session/{id}/end`

### `GET /voice/students/{student_id}/latest`
Most recent session summary — used to offer "continue where you left off".

### `GET /curriculum/courses`
The catalogue the tutor can teach, grouped by course. Each topic carries its
`summary`, `level`, `minutes`, `concepts`, suggested `questions` and `sections`
(the lesson plan).

```json
{
  "courses": [
    {
      "id": "algorithms-101",
      "title": "Algorithms & Data Structures",
      "subject": "Computer Science",
      "topic_count": 5,
      "topics": [
        {
          "id": "binary-search",
          "title": "Binary Search",
          "sections": [{"title": "The idea of halving", "goal": "compare with the middle, …"}],
          "concepts": ["sorted input", "midpoint", "O(log n)"]
        }
      ]
    }
  ],
  "count": 5,
  "stats": {"courses": 5, "topics": 22, "sections": 88}
}
```

`?with_topics=false` returns the course list alone (lighter for a menu).

### `GET /curriculum/topics`
Flat topic list, filterable by `course_id` and `level`.

### `POST /voice/session/{session_id}/level` → `200`

Re-pitch the explanation of the lesson in progress for another level. The
learning state is untouched: the same topic, the same checkpoint, the same
concepts, explained differently — and `explanation.planned` is emitted again.

```json
{ "level": "advanced" }
```

Response (`SimpleResponse`): `{"session_id": "...", "state": "listening",
"detail": "level=advanced"}`. An unrecognised level is a `422`.

### `GET /curriculum/topics/{topic_id}`
One topic plus its course. `404` for an unknown id.

### `GET /voice/languages`
Static capability documentation for all ten languages: name, primary pipeline,
fallback pipelines, `realtime_native`.

### `GET /health`
Public liveness: `{"status": "ok", "service": "lerna-voice-ai"}`.

### `GET /health/providers`
Configured vendors, routing mode, per-vendor circuit-breaker state, the
capability matrix and the per-language plan. Never contains secrets.

## Error format

Every error — REST or WebSocket — uses one envelope:

```json
{
  "event": "error",
  "code": "VOICE_PROVIDER_UNAVAILABLE",
  "message": "Voice service is temporarily unavailable.",
  "recoverable": true,
  "details": null
}
```

### Error codes

| Code | HTTP | Recoverable |
|---|---|---|
| `VOICE_REQUEST_INVALID` | 422 | no |
| `VOICE_SESSION_NOT_FOUND` | 404 | no |
| `VOICE_SESSION_INVALID_STATE` | 409 | yes |
| `VOICE_AUTH_REQUIRED` | 401 | no |
| `VOICE_LANGUAGE_UNSUPPORTED` | 422 | no |
| `VOICE_CAPABILITY_UNSUPPORTED` | 422 | no |
| `VOICE_AUDIO_MALFORMED` | — (WS) | yes |
| `VOICE_PROVIDER_UNAVAILABLE` | 503 | yes |
| `VOICE_PROVIDER_TIMEOUT` | 504 | yes |
| `VOICE_PROVIDER_RATE_LIMITED` | 429 | yes |
| `VOICE_PROVIDER_QUOTA_EXHAUSTED` | 503 | no |
| `VOICE_PROVIDER_AUTH_FAILED` | 502 | no |
| `VOICE_RAG_UNAVAILABLE` | — | yes (tutor continues without evidence) |
| `VOICE_PERSISTENCE_UNAVAILABLE` | — | yes (session continues in memory) |
| `VOICE_CONNECTION_LOST` | — (WS) | yes |
| `VOICE_INTERNAL_ERROR` | 500 | no |

Stack traces are never returned when `APP_ENV=production`.
