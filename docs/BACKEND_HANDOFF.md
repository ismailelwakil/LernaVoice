# Backend handoff contract

What the LERNA backend and web/mobile teams need in order to integrate this
service. Nothing here requires changing the voice service.

## Division of responsibility

| Concern | Owner |
|---|---|
| Student auth, courses, enrolment, UI | LERNA backend / frontend |
| Creating voice sessions, minting client tokens | LERNA backend |
| Microphone capture, playback, barge-in UX | Client |
| Streaming, providers, failover, checkpoints, resume | **Voice service** |
| RAG, Progress Profile, Orchestrator | LERNA Academic OS (called by the voice service) |

## Sequence

```
browser            LERNA backend              voice service
  │  "start voice lesson"  │                         │
  ├───────────────────────►│                         │
  │                        │ POST /voice/session     │   X-Voice-Service-Key
  │                        ├────────────────────────►│
  │                        │◄── 201 {session_id,...} │
  │                        │ POST /voice/session/{id}/token
  │                        ├────────────────────────►│
  │◄── {session_id, ws_url, token} ─────────────────┤
  │                                                  │
  │  WS /voice/session/{id}/audio?token=vst_...      │
  ├─────────────────────────────────────────────────►│
  │  binary PCM16 16 kHz  ⇄  JSON events             │
```

The service key must never reach the browser. Tokens are single-session and
expire in 15 minutes; mint a fresh one per connection attempt.

## Backend responsibilities

1. **Create the session** with `student_id`, `language`, `course_id`,
   `lesson_id`, `topic`, optional `document_ids`.
2. **Offer continuation**: call `GET /voice/students/{student_id}/latest`; if a
   session exists for the lesson, create the next one with
   `resume_latest: true` so the student gets a recap instead of a restart.
3. **Mint tokens** on demand for the client.
4. **Do not** proxy audio. The client talks to the voice service directly.
5. Optionally mirror `session.ended` summaries into your own analytics; the
   Progress Profile is already updated by the service.

## Client responsibilities

| Requirement | Detail |
|---|---|
| Mic capture | PCM16, **16 kHz**, mono, little-endian; 20–100 ms chunks as binary WS frames |
| Playback | PCM16, **24 kHz**, mono — constant across every provider |
| Barge-in | On `assistant.interrupted` (`stop_playback: true`) stop the audio sink **immediately**, before any other handling |
| Dedupe | Use `seq`; after reconnect ignore anything `<= last_seq` from the replayed `session.state_changed` |
| Reconnect | Same URL with a fresh token; state is replayed, the lesson does not restart |
| Keepalive | `{"type":"ping"}` every ~20 s |
| Visuals | Render `visual.updated` payloads (`code`, `equation`, `diagram`, `image`) |
| Errors | Show `message`; retry only when `recoverable: true` |

## Events a UI should handle at minimum

`session.started`, `session.recap`, `input.transcript`, `assistant.text.delta`,
`assistant.audio.chunk`, `assistant.interrupted`, `assistant.response.completed`,
`checkpoint.created`, `question.started/completed`, `resume.started/completed`,
`visual.updated`, `language.changed`, `provider.switched`, `error`,
`session.ended`.

Full list: [`WEBSOCKET_PROTOCOL.md`](WEBSOCKET_PROTOCOL.md).

## Guarantees the service gives you

* A provider failure mid-lesson does not lose the session, language, checkpoint,
  questions or misconceptions — you will see `provider.switched` and the
  conversation continues.
* Output audio format never changes across failover.
* All ten languages are served; `GET /voice/languages` tells you which are
  native-realtime and which are composed (today only Igbo is composed).

## Things you must not assume

* That Igbo or Yoruba have multi-vendor redundancy — they do not (see
  `FAILOVER.md`).
* That sessions are portable between workers without sticky routing.
* That the Streamlit app is a frontend — it is a test harness.
