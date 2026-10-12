# How the voice tutor works

## What a turn sounds like, not just how it reads

A lesson plan is a *note to the tutor*. Spoken aloud, "Step two — Trace it on a
small array — walk through 16 elements down to 8, 4, 2, 1" sounds like a machine
reading a checklist, and that is the one thing a voice tutor must never do. Two
rules keep it human, and both are enforced by tests:

1. **Every turn is a sentence in the session language.** The plan's title and goal
   are wrapped in rotating spoken frames (`STEP_LEAD`, `MOVE_ON`, `REACT` for all
   ten languages in `app/prompts/interaction.py`) rather than recited with
   labels. Four leads, five transitions and four reactions per language, chosen
   by step index, so two consecutive steps never open the same way.
2. **What reaches the synthesiser is words, not symbols.** `speakable()` normalises
   the transcript before it is voiced — `mid = (low + high) // 2` becomes
   *"mid equals low plus high divided by 2"*, `n >= 100` becomes *"n greater than
   or equal to 100"*, `O(n log n)` becomes *"On log n"*, brackets are dropped and
   em dashes become commas. The service applies it server-side for the audio it
   synthesises; `app/static/voice_mode.html` applies the identical function to the
   text it hands to the browser's `speechSynthesis`.

The consequence is that the mock tutor (which is what you hear without vendor
credentials) speaks in sentences too: "Mhm. Take your time, I'll wait." instead of
an empty acknowledgement, three genuinely different routes for a confused student
(rephrase → put simply → smaller step), and a **no-repeat guarantee** — a
sentence already used in the session is never said twice.

With real credentials this matters less (the model writes its own sentences) but
it still applies: the `speakable()` step runs on the vendor's transcript before
`gemini-3.8-live` / ElevenLabs TTS sees it, which is where "slash slash" used to
creep into spoken maths.

## Turn lifecycle

```
idle ─start─► connecting ─► listening ⇄ thinking ─► speaking
                                   ▲                   │
                                   └──── interrupt ────┘
                                            │
                                   interrupted ─► answering ─► resuming ─► speaking
                                                                   │
                                                               paused / ended
```

The student's microphone streams continuously. Turn detection is the provider's
native VAD when available (Gemini Live, ElevenLabs `commit_strategy=vad`,
Deepgram `UtteranceEnd`); clients that prefer their own VAD can send
`audio_start` / `audio_end` markers.

## Barge-in (§23)

Interruption is treated as the highest-priority event in the system:

1. The server emits `assistant.interrupted` with `stop_playback: true` **first**,
   before any other work. The client's only job is to kill its audio sink
   immediately — this is what makes it feel human.
2. The provider is told to cancel generation (native interrupt for Gemini Live;
   cancel LLM + TTS for a cascade).
3. A checkpoint is created from the current learning state.
4. A short acknowledgement in the session language is produced
   (Arabic: *«طبعًا، اتفضل اسأل سؤالك.»*).
5. The session moves to `interrupted`, waiting for the question.

Ordering is asserted in tests: `assistant.interrupted` always precedes
`checkpoint.created`.

## Checkpoints are learning state, not timestamps (§24)

```json
{
  "checkpoint_id": "cp_9a2c...",
  "topic": "Binary Search",
  "section": "Choosing the midpoint",
  "concepts_covered": ["sorted array", "low pointer", "high pointer"],
  "next_step": "Explain why the midpoint halves the search space",
  "resume_instruction": "Continue from the midpoint explanation. Do not repeat the definition.",
  "created_at": 1765432100.2
}
```

Nothing in there is an audio offset. Resuming works even if the provider, the
socket, the process or the day has changed.

## Questions and follow-ups (§25–§26)

* Any number of interrupt → question → follow-up → resume cycles per lesson.
* A question asked while an interruption is still open is automatically marked
  `is_followup: true`, and the tutor keeps the previous question in context.
* Each question is retrieved against LERNA's RAG before answering
  (`rag.retrieved`), so answers stay grounded in the student's own materials.
* Questions are stored on the session with `answered` status; anything left
  unanswered at the end becomes an `unresolved_question` the next session can
  pick up.

## Smart resume (§27)

The resume prompt is built from the checkpoint and explicitly instructs the
tutor to continue, list what is already covered, and **not** repeat it. The
session never re-runs the lesson intro. `resume.started` → `resume.completed`
bracket the transition and `resume_count` increments.

## Returning students (§28)

`POST /voice/session {"resume_latest": true}` forks the student's last session
for the lesson into a new session that inherits topic, section, concepts,
checkpoint and unresolved questions, with `previous_session_id` recorded.
On start the service emits `session.recap` and prompts the tutor to give a brief
recap before continuing — not to start over.

## Tools the model can call (§32)

| Tool | Effect |
|---|---|
| `retrieve_course_material` | RAG lookup in the student's documents; emits `rag.retrieved`. |
| `show_visual` | Emits `visual.updated` with `{type: code\|equation\|diagram\|image, content, language?, caption?}`. |
| `record_learning_signal` | `concept_understood`, `misconception_detected`, `struggling`, `mastered` → `learning.signal` + Progress Profile write-back. |
| `update_lesson_position` | Moves topic/section so checkpoints stay accurate. |

## Latency instrumentation

`LatencyTracker` measures `provider_connect`, `speech_to_first_audio`,
`question_to_first_audio`, `resume_to_audio`, `failover_total`. Each closed span
emits a `latency` event and is summarised in `/voice/session/{id}/state`
diagnostics.

Expected turn latency: ~300–600 ms on a native Gemini Live pipeline, ~600–1200 ms
on a cascade. These are design expectations from the vendors' published figures,
not measurements taken in this environment.

## Privacy

* Raw audio is **not** persisted (`VOICE_STORE_RAW_AUDIO=false` by default); it
  is streamed to the provider and dropped.
* Transcripts and learning state are stored because the tutor needs them to
  resume and to update the Progress Profile (`VOICE_STORE_TRANSCRIPTS=true`).
* Logs are structured JSON and run through a redactor that strips API keys and
  connection strings.
* Provider credentials never leave the server; browsers get a 15-minute
  single-session token instead.
