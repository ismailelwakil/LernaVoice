# Failover and resilience

## The guarantee

> A provider failure may cost the student a second of audio. It may **never**
> cost them the lesson.

Across any failover the service preserves: session id, language, lesson/topic/
section, concepts covered, the active checkpoint, every question asked (and
whether it was answered), unresolved questions, detected misconceptions,
interrupt/resume counters and provider history. Verified by
`tests/provider/test_failover.py::test_failover_preserves_the_entire_session`
and the full §55 scenario in `tests/e2e/`.

## Error classification

`app/providers/base.py` maps every vendor failure onto an `ErrorClass`:

| Class | Examples | Retry? | Opens circuit? |
|---|---|---|---|
| `TRANSIENT` | socket reset, 5xx | yes | yes |
| `TIMEOUT` | no first audio in time | yes | yes |
| `RATE_LIMIT` | 429 | yes (backoff) | yes |
| `QUOTA` | credit exhausted | **no** | yes |
| `AUTH` | bad/expired key | **no** | yes (immediately) |
| `UNSUPPORTED` | language/capability gap | **no** | no (routing fact, not a fault) |
| `MALFORMED_AUDIO` | bad client frame | no | no (client error) |
| `INTERNAL` | our bug | yes once | yes |

Auth and quota failures skip retries entirely and go straight to fallback —
retrying a wrong key just wastes the student's time.

## Retry policy

`VOICE_MAX_RETRIES` (default 2) attempts per pipeline, exponential backoff from
`VOICE_RETRY_BACKOFF` (default 1 s → 1 s, 2 s), each attempt bounded by
`VOICE_PROVIDER_TIMEOUT`. Every attempt emits `provider.retrying`.

## Circuit breaker

`ProviderHealthRegistry` tracks per-vendor consecutive failures. After
`VOICE_CIRCUIT_BREAKER_THRESHOLD` (3) the vendor is marked unhealthy and skipped
by the router for `VOICE_CIRCUIT_BREAKER_COOLDOWN` seconds (60), then allowed a
probe. A success resets the counter. State is visible at `/health/providers`.

## Fallback chain

1. Compute every pipeline that can serve the language (capability registry).
2. Score: realtime beats cascade; fewer vendors beats more; higher-priority
   vendors beat lower; already-failed signatures are excluded; unhealthy vendors
   are filtered out.
3. Connect to the best one. On failure, record the transition and try the next.
4. If every candidate is exhausted, emit a recoverable
   `VOICE_PROVIDER_UNAVAILABLE` error and move the session to `error` — the
   session document and checkpoint remain intact so the student can retry.

Each step emits `provider.fallback_started` → `provider.selected` →
`provider.connected` → `provider.switched`.

## Mid-lesson switch

When the active provider dies while the tutor is speaking:

1. Checkpoint the current learning state (if not already checkpointed).
2. Tear down the dead provider.
3. Select the next pipeline and connect it.
4. Rebuild the system instruction with language + lesson context + checkpoint +
   recent conversation, so the new provider resumes mid-thought.
5. Publish the lesson position with the config (`metadata.step_index`, derived
   from `state.current_section`), so the new pipeline continues the same plan
   step instead of starting the lesson again. Providers report their position
   through the `update_lesson_position` tool, which is what keeps it accurate.
6. Emit `provider.switched` with `continuity: true`.

## Failover test matrix (§54)

All of these run on mock providers with injected faults — `pytest tests/provider -q`.

| Scenario | Expected | Test |
|---|---|---|
| Gemini healthy | stays on `realtime:gemini`, no fallback events | `test_gemini_success_no_fallback` |
| Gemini fails once, then recovers | one `provider.retrying`, no fallback, still Gemini | `test_gemini_temporary_failure_then_recovers` |
| Gemini permanently down | cascade without any Gemini component (EL STT + LERNA LLM) | `test_gemini_permanent_failure_falls_back` |
| Gemini + ElevenLabs down | Deepgram STT/TTS + LERNA LLM, ≥2 fallback events | `test_elevenlabs_failure_moves_to_deepgram_components` |
| Everything down | graceful `VOICE_PROVIDER_UNAVAILABLE`, session state `error`, no crash | `test_all_providers_fail_gives_graceful_error` |
| Auth failure | no retry, immediate fallback | `test_auth_failure_is_not_retried` |
| Failure mid-lesson | full continuity, `provider.switched` | `test_failover_preserves_the_entire_session` |
| Repeated failures | circuit opens, vendor skipped | `test_circuit_breaker_avoids_a_just_failed_provider` |
| Unsupported language in `gemini_only` | `VOICE_LANGUAGE_UNSUPPORTED`, no silent language swap | `tests/unit/test_capabilities_and_router.py` |

## What failover cannot fix

* **Igbo STT** — ElevenLabs is the only vendor. If it is down, Igbo voice input
  is down; the session reports a recoverable provider error rather than
  pretending to understand.
* **Yoruba TTS** — Gemini only.
* **sw/am/ha/so/zu** — Deepgram contributes nothing, so the practical chain is
  Gemini → ElevenLabs(+LERNA LLM) and then nothing.

These gaps are vendor coverage facts, not implementation shortcuts, and they are
reported honestly at `/health/providers` and `/voice/languages`.
