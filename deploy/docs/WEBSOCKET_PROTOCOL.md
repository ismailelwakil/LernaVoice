# WebSocket protocol

```
WS /voice/session/{session_id}/audio?token=<vst_token>
```

Authentication: either a short-lived session token in `?token=` (issued by
`POST /voice/session/{id}/token`) or the service key in the
`X-Voice-Service-Key` header. Close codes:

| Code | Meaning |
|---|---|
| `4401` | Unauthorised (missing/expired token) |
| `4404` | Unknown session id |
| `4500` | Internal error |

## Frame types

| Direction | Frame | Payload |
|---|---|---|
| client → server | **binary** | raw PCM16, **16 kHz**, mono, little-endian. Any chunk size up to 64 KiB; 20–100 ms recommended. |
| client → server | **text** | JSON control message, `{"type": "..."}`. |
| server → client | **text** | JSON event envelope (below). Assistant audio arrives base64-encoded inside `assistant.audio.chunk`, so a client only needs one parser. |

Assistant audio is always **PCM16, 24 kHz, mono, little-endian**, regardless of
which vendor produced it. The decoder never has to change across failover.

## Event envelope

```json
{
  "event": "assistant.audio.chunk",
  "seq": 42,
  "session_id": "vs_8f1c...",
  "ts": 1765432100.231,
  "audio": "UklGRi4A...",
  "sample_rate": 24000
}
```

`seq` increases monotonically per session. After a reconnect the server replays
a `session.state_changed` frame containing `last_seq`; discard anything you have
already applied.

## Client → server control messages

| `type` | Fields | Effect |
|---|---|---|
| `start` | `recap` (optional bool) | Begin the lesson. Omit `recap` to let the server decide (returning students get a recap automatically). |
| `audio` | `audio` (base64 PCM16) | Fallback for clients that cannot send binary frames. |
| `audio_start` / `audio_end` | — | Optional markers around a student utterance; useful when the client does its own VAD. |
| `text` | `text` | Send a text turn (accessibility / typed input). |
| `interrupt` | `source` (optional) | **Barge-in.** Stop the tutor now. |
| `question` | `text` | Interrupt (if needed) and ask a question. |
| `resume` | — | Continue the lesson from the checkpoint. |
| `language` | `language` (ISO-639-1) | Switch language mid-session. The tutor acknowledges **in the new language** and continues the current plan step — no reconnect from the client, no restart of the lesson. All learning state and the plan position are kept. |
| `pause` / `unpause` | — | Suspend / restore the session. |
| `end` | — | Finish the session and write the summary. |
| `ping` | — | Keepalive; answered with `pong`. |

## Server → client events

### Session
| Event | Key fields |
|---|---|
| `session.started` | `language`, `pipeline`, `course_id`, `lesson_id` |
| `session.state_changed` | `from_state`, `to_state`, `last_seq`, `pipeline`, `checkpoint` |
| `session.recap` | `previous_session_id`, `topic`, `concepts_covered`, `unresolved_questions` |
| `session.paused`, `session.resumed` | `state` |
| `session.ended` | `summary`, `duration_ms`, `interrupt_count` |

### Audio & transcript
| Event | Key fields |
|---|---|
| `audio.input.started` / `audio.input.ended` | — |
| `audio.input.chunk` | `bytes` (diagnostic only) |
| `input.transcript` | `text`, `final` |
| `assistant.response.started` | — |
| `assistant.text.delta` | `text` |
| `assistant.audio.chunk` | `audio` (base64), `sample_rate` |
| `assistant.response.completed` | `text` |
| `assistant.interrupted` | **`stop_playback: true`**, `reason` |

> **Client contract:** on `assistant.interrupted`, flush and stop the audio sink
> *before* doing anything else. This is what makes barge-in feel instant.

### Learning
| Event | Key fields |
|---|---|
| `explanation.planned` | `topic_id`, `topic`, `level`, `grounding` (`curated`\|`catalogue`), `teaching_order`, `move_count`, `sources[]`, `sources_used` — what the tutor is about to teach from, sent when the lesson starts and again when the level changes |
| `checkpoint.created` | `checkpoint {checkpoint_id, topic, section, concepts_covered, next_step, resume_instruction}` |
| `question.started` / `question.completed` | `question_id`, `text`, `is_followup` |
| `resume.started` / `resume.completed` | `checkpoint_id`, `resume_count` |
| `language.changed` | `from`, `to`, `dialect`, `previous_dialect`, `pipeline`, `checkpoint_preserved` — Arabic is reported with its register (`to: "ar"`, `dialect: "ar-MSA"`), which no longer changes: the lesson is always fusHa. |
| `learning.signal` | `kind`, `concept` (always English — see `docs/PROGRESS_PROFILE.md`), `confidence`, `spoken_as`?, `language`?, `canonical`, `catalogue_ref`? |
| `visual.updated` | `visual {type: code\|equation\|diagram\|image, content, language?, caption?}` |
| `rag.retrieved` | `query`, `chunks`, `sources` |

### Provider / diagnostics
| Event | Key fields |
|---|---|
| `provider.selected` | `pipeline`, `providers`, `reason` |
| `provider.connected` | `pipeline`, `connect_ms`, `retry_count` |
| `provider.failed` | `provider`, `error_class`, `message` |
| `provider.retrying` | `provider`, `attempt`, `delay_ms` |
| `provider.fallback_started` | `from`, `reason` |
| `provider.switched` | `from`, `to`, `continuity: true` |
| `latency` | `span`, `ms` |
| `error` | `code`, `message`, `recoverable`, `details` |
| `pong` | — |

Error codes are enumerated in [`API.md`](API.md#error-codes).

## Minimal client sketch

```js
const ws = new WebSocket(`${base}/voice/session/${id}/audio?token=${token}`);
ws.binaryType = "arraybuffer";

ws.onopen = () => ws.send(JSON.stringify({ type: "start" }));

ws.onmessage = (frame) => {
  const e = JSON.parse(frame.data);
  switch (e.event) {
    case "assistant.audio.chunk": player.enqueue(b64ToPcm(e.audio)); break;
    case "assistant.interrupted": player.stopNow(); break;   // §23
    case "checkpoint.created":    ui.showCheckpoint(e.checkpoint); break;
    case "visual.updated":        ui.renderVisual(e.visual); break;
    case "provider.switched":     ui.note(`switched to ${e.to}`); break;
  }
};

// microphone: 16 kHz PCM16 chunks
micWorklet.onchunk = (pcm) => ws.send(pcm);

// barge-in
interruptButton.onclick = () => {
  player.stopNow();                                   // stop locally first
  ws.send(JSON.stringify({ type: "interrupt" }));
};
```
