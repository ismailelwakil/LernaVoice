# Testing

```bash
pip install -r requirements.txt
pytest -q
```

**No test requires a paid credential, a network connection or a database.**
Every vendor is replaced by a mock implementing the same interface, and the
in-memory repository backs persistence.

## Suites

| Path | What it covers | Tests |
|---|---|---|
| `tests/unit/` | capability registry, routing/scoring, provider modes, health registry, circuit breaker, error classification, course catalogue integrity, **the interaction layer** (behaviour contract, phrase/template coverage in 10 languages, intent classification, dialogue policy, **how a step sounds when spoken** — sentence frames, rotation, `speakable()` normalisation, plus the live-voice setup payload, credential loading and setup hints, **curated plan translations**, **the ElevenLabs two-transport policy**, **English-only concept storage**, **the Azure free-tier voice**, **the coverage gate**, **Arabic's fusHa register, the Egyptian aliases that normalise to it, and the request shape that accepts them**, **the levels, the vetted sources and the explanation builder**, **how the tutor teaches a whole pass at a time**, **and how a question is answered from the material**) | **252** — includes `test_demo_voice.py`: which vendor voices the offline demo, the vendor's bytes reaching the student, the synthetic fallback when a vendor fails, and the key never reaching the browser (18 tests); `test_elevenlabs_transport.py` (12) pins the ws-vs-REST policy the live API forced on us; `test_curriculum_localisation.py` (6) keeps Arabic sessions Arabic; `test_canonical_concepts.py` (11) proves the profile stores English whatever the tutor speaks; `test_azure_tts.py` (7) pins the Azure request/response contract offline; three more demo-voice tests pin the coverage gate that stops a vendor being asked for a language it has no voice for; `test_teacher_mode.py` (17) pins the teaching behaviour — a turn is several sentences developing one part of the lesson, not one line plus "any questions?": pass length per level, one pass per lesson section, questions not after every pass, a question answered from the pack and then teaching continues, confusion re-teaching by another route, no sentence repeated in a session, Arabic staying Arabic, the teacher still answering once the plan runs out, and a question being answered with the pack sentence that actually bears on it rather than the next one in rotation; `test_explanation_engine.py` (35) pins the round-19 layer: level spellings, what each level demands, the vetted packs, the move order per level, the closing question staying last, the grounded prompt block, the Arabic moves carrying their English original, the profile round-trip and the request > LERNA > store > default precedence; `test_arabic_dialects.py` (24) pins the formal register — the voice it gets, the SSML (style, pauses, emphasis), the fusHa phrase table, the Egyptian spellings that normalise to `ar-MSA` instead of failing, and the style-refusal retry |
| `tests/integration/` | session lifecycle, interruption ordering, checkpoints, follow-ups, resume, tools/visuals, **the language switch being spoken in the new language and the lesson position surviving it**, persistence round-trip, manager restart, served demo pages, curriculum API + session plans, **the grounded explanation over REST and the socket** | 58 |
| `tests/provider/` | the §54 failover matrix, continuity across switch, cascade internals, sentence chunking, mock audio quality + turn detection, **lesson-plan teaching and the conversational reply policy** | 29 |
| `tests/multilingual/` | all 10 languages × full cycle, prompt coverage, documented pipeline per language, Igbo end-to-end | 24 |
| `tests/websocket/` | REST contract, WS control messages, event ordering/`seq`, reconnect replay, token auth, no-secret-leak checks | 12 |
| `tests/e2e/` | the complete §55 scenario and event-order coherence | 2 |
| `tests/browser/` | the demo client's audio path and the topic picker — JS extracted and run in Node against stubbed DOM/Web Audio/Web Speech APIs (PCM scheduling, resampling, voicing, barge-in, deep links, course switching, **opaque-origin preview iframes**, **the voice being fed words rather than symbols**, **the voice following a language switch and admitting a missing one**). Skipped if Node is absent | 18 |
| **Total** | | **395 passing** |

## Mock providers and fault injection

`app/providers/mock/providers.py` provides `MockRealtimeProvider`,
`MockSTTProvider`, `MockTTSProvider`, `MockLLMProvider`, `MockRAGProvider` and a
global `INJECTOR`:

```python
from app.providers.mock.providers import INJECTOR

INJECTOR.fail("gemini", "internal")            # until healed
INJECTOR.fail("gemini", "timeout", times=1)    # one transient blip
INJECTOR.fail("elevenlabs", "auth")            # no-retry class
INJECTOR.heal()                                # autouse fixture does this per test
```

Fault kinds map onto the real `ErrorClass` values, which is what makes the
failover tests meaningful rather than cosmetic.

## Fixtures (`tests/conftest.py`)

| Fixture | Gives you |
|---|---|
| `settings` | test `Settings` (memory persistence, LERNA disabled, no auth, fast retries) |
| `mock_factory` | real `ProviderFactory` wired to mocks for all four vendors |
| `router` | real `VoiceProviderRouter` over the real capability registry |
| `repository` | `InMemoryVoiceRepository` |
| `progress`, `orchestrator`, `rag` | stub LERNA adapters that record what was written |
| `manager`, `session` | a ready `VoiceSessionManager` / `VoiceSession` |
| `recorder` | `EventRecorder` — subscribe, `drain()`, `has()`, `of()`, `types()` |

## Writing a new test

```python
async def test_my_behaviour(session, recorder):
    rec = recorder(session)
    await session.start()
    await session.interrupt()
    await rec.drain()
    assert rec.has(EventType.CHECKPOINT_CREATED)
```

`pytest.ini` sets `asyncio_mode=auto`, so `async def` tests need no decorator.

## What the tests deliberately do not cover

* **Live vendor sockets.** Gemini Live, ElevenLabs and Deepgram clients are
  written to their documented protocols but are not exercised against real
  endpoints here. Treat the first run with real keys as integration bring-up and
  watch `/health/providers`.
* **Real MongoDB.** `MongoVoiceRepository` is checked for interface completeness
  against the abstract repository; a live Atlas smoke test is a deployment step.
* **Audio quality / ASR accuracy.** Vendor-side concerns; the per-language
  accuracy expectations are documented in `LANGUAGES.md`.
* **Load and concurrency limits.** No load test is included.

## Running the real service with no credentials

```bash
VOICE_ENABLE_MOCK_PROVIDERS=true LERNA_INTEGRATION_MODE=disabled \
  uvicorn app.main:app --port 8080
```

In this mode the vendor names (`gemini`, `elevenlabs`, `deepgram`, `lerna`) are
served by mock implementations, so the real router, cascade builder, failover
logic, WebSocket protocol and Streamlit panel all work offline with synthetic
audio. It is a development switch only — never enable it in production.

## Audio-path tests

Two suites exist specifically because "the demo makes no sound" is a failure
mode that ordinary unit tests cannot see:

`tests/provider/test_mock_audio.py` checks the mock vendors of the offline demo:
the generated PCM is a real waveform (the original implementation emitted a
constant DC offset, which is silence), it is loud enough to hear, a reply is
long enough to listen to and arrives in multiple chunks, and turn-taking is
driven by a **pause** — continuous speech yields exactly one reply, while a
stray PCM frame yields none.

`tests/browser/test_client_audio.py` extracts the client JavaScript out of
`streamlit_app/app.py`, runs it in Node against a stubbed `AudioContext`, and
asserts on the schedule it produces: every chunk is played, chunks are placed
back-to-back with no gap or overlap, playback starts on the first chunk instead
of waiting for the turn to finish, a 48 kHz output device still receives the
full 100 ms at the right pitch, and `assistant.interrupted` stops playback.

```bash
pytest tests/provider/test_mock_audio.py tests/browser -v
```

Node is optional — without it the browser suite reports as skipped, and the
other 92 tests still run.

## Page-serving tests

`tests/integration/test_served_pages.py` pins the browsing contract: `/` serves
the voice screen, the page is self-contained (no CDN — hosted previews have no
network), its default config is **origin-relative**, it lists all ten mandatory
languages, and no provider credential can reach it.

### Voice-output tests

`test_assistant_is_voiced_sentence_by_sentence` asserts each sentence is spoken
exactly once — never twice at turn end, which is the classic bug when a client
speaks both the streaming deltas and the final transcript.
`test_interrupt_silences_the_voice` covers the barge-in requirement for the
speech engine, and `test_voice_engines_are_selectable` checks that switching to
the PCM engine plays service audio while the browser voice stays silent, and
that PCM bytes are still counted in browser mode.

### Curriculum tests

`tests/unit/test_curriculum.py` checks the catalogue is complete and teachable
(unique ids, ≥3 steps and ≥3 concepts per topic, resolvable by id, title or free
text, greetings for all ten languages).
`tests/integration/test_curriculum_api.py` drives the picker's path over the API:
list courses → create a session with a `topic_id` → assert the state, the system
instruction and the provider metadata all carry the plan, and that a composed
language (`ig`) reports `cascade:elevenlabs+gemini+gemini` **before** connecting.
`tests/provider/test_mock_audio.py` asserts both the realtime mock and the LLM
mock (composed pipelines) walk the plan step by step.
