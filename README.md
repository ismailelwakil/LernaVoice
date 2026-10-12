# LERNA Voice AI Service

Real-time, multilingual, interruptible **voice tutor** for LERNA. A standalone
Python/FastAPI service that streams audio both ways over a WebSocket, routes
across multiple AI vendors, and reuses LERNA's existing RAG, Progress Profile
and Learning Orchestrator instead of building a second tutor.

> **Status:** feature-complete against the implementation spec, with 395 passing
> automated tests that run **without any paid credentials** (mock providers).
> Two voices have been exercised against live keys: **ElevenLabs v4** and
> **Azure AI Speech** (free F0 tier, `germanywestcentral`). Gemini Live is
> implemented but still blocked by Google billing; Deepgram is untested against
> a live key — see [Known limitations](#known-limitations).

---

## What it does

| Capability | Summary |
|---|---|
| Streaming conversation | Continuous PCM16 in, PCM16 out over one WebSocket. Not record → upload → transcribe. |
| Barge-in | Student can interrupt at any moment; the client stops playback **immediately** on `assistant.interrupted`. |
| Smart checkpointing | Checkpoints capture *learning state* (topic, section, concepts covered, next step), not audio timestamps. |
| Unlimited Q&A cycles | Interrupt → ask → follow-up → resume, as many times as the student wants. |
| Smart resume | The tutor continues from the checkpoint; it never restarts the lesson. |
| Returning students | A later session inherits the checkpoint and opens with a recap. |
| Conversational tutoring | Teaches continuously and reacts to the answer — *not* a quiz after every step. "I don't understand" gets a different route, never the same paragraph again. Wording rotates instead of repeating, and a live language switch is acknowledged in the new language. |
| 10 languages | English, **Arabic (Modern Standard Arabic, `ar-MSA`)**, French, Swahili, Amharic, Hausa, Somali, Yoruba, Igbo, Zulu — selectable mid-lesson. |
| Multi-provider | Gemini primary, ElevenLabs backup #1, Deepgram backup #2, composable per component. |
| Automatic failover | Health tracking, circuit breakers, retries with backoff, mid-lesson provider switch with **zero session loss**. |
| Visual learning events | `visual.updated` carries code, equations and diagram specs for the UI. |
| LERNA integration | RAG retrieval, Progress Profile signals, Learning Orchestrator next-action. |

### How the tutor converses (not just reads)

The behaviour contract lives in `app/prompts/interaction.py` and is appended to
**every** system instruction, so it survives reconnects, failovers and language
changes: teach one idea then stop and check, react to what the student actually
said, name the specific gap when they are wrong, rephrase with a *different*
route when they say they don't understand, ask one question at a time, never read
the plan aloud. The same behaviour exists as speakable lines in the ten languages,
which is what the offline mock tutor uses — so the demo can be driven
conversationally with no vendor keys:

| You say | The tutor does |
|---|---|
| "yes" / "نعم" / "yebo" | teaches the next step — and often keeps going into the one after it instead of asking you to confirm again |
| "I don't understand" / "مش فاهم" | rephrases by another route (plainer words → smaller step → example), never the same sentence twice, and does not lecture you for asking |
| "what is the midpoint?" | answers, stays on the current step, invites a follow-up |
| *(nothing — you just let it talk)* | keeps teaching; it only asks something when it earns its place |
| *(switches language in the picker)* | acknowledges **in the new language** and continues the same step |

Rules the tutor is held to (asserted in `tests/unit/test_interaction_layer.py`): never
reuse a sentence inside a session, never use an "is that clear?"-style check-in, vary how
every turn opens, and use your name occasionally rather than constantly.

---


## Quick start

```bash
cd voice-ai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill in the keys you have

uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Then:

```bash
curl localhost:8080/health
curl localhost:8080/voice/languages | jq '.languages[] | {code, realtime_native}'
```

### Turning on the real voice

The demo runs with mock providers by default so it is testable with no keys. For the real
Gemini voice, fill `.env` and start the service **without** `VOICE_ENABLE_MOCK_PROVIDERS`:

```bash
# A) Vertex AI / Agent Platform  → gemini-3.8-live  (native audio)
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-project
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# B) Gemini Developer API       → gemini-2.5-flash-native-audio-preview-12-2025
GOOGLE_GENAI_USE_VERTEXAI=false
GEMINI_API_KEY=AIza...            # a Developer API key, not an OAuth token

uvicorn app.main:app --port 3000  # no VOICE_ENABLE_MOCK_PROVIDERS
curl localhost:3000/health        # -> {"mock_providers": false, "gemini_auth": "vertex", ...}
```

`/health` reports which model each path would use (`live_models`), whether the mock is
running, and which auth the service actually resolved — never a credential. When the
service is live, the demo screen plays the vendor's own voice by default (it only voices
the transcript itself when the audio is the mock's synthetic PCM).

Demo harness (testing only, **not** the production frontend):

```bash
# no vendor keys? run the service with mock providers and the whole
# routing / cascade / failover machinery still works end to end:
VOICE_ENABLE_MOCK_PROVIDERS=true uvicorn app.main:app --port 3000

# the voice screen is served by the service itself, same origin as the API and
# the WebSocket, so `/` needs no cross-port configuration:
open http://localhost:3000/topics      # pick a topic + language, start a lesson
open http://localhost:3000/            # voice screen (alias: /voice)
open http://localhost:3000/console     # lower-level console: raw events, controls
streamlit run streamlit_app/app.py     # optional: the same screen inside Streamlit
```

`/` is served from `app/static/voice_mode.html`; the Streamlit harness embeds
that same file, so there is one implementation. Keep the page on the service's
own port for hosted/preview deployments — a port-proxy will happily serve the
page but block the cross-port `fetch`/WebSocket that an embedded copy needs.

In demo mode the mock vendors synthesise **audible** speech-like audio (they do
not return silence), so the voice loop can be tested with your ears: press the
blue **●** to connect — that also unlocks the browser's audio — then talk, or
press **+** for synthetic input. `bash run_demo.sh` starts both processes at
once (service on `:3000`, voice screen on `:8501`).

| Control | Does |
|---|---|
| **● / ■** | connect / end the session |
| **🎤** | microphone on/off — streams PCM16 @ 16 kHz to the service |
| **🎙** | interrupt (barge-in) — kills playback locally on the same tick |
| **+** | send 0.5 s of synthetic PCM16 @ 16 kHz (no microphone needed) |
| type + Enter | ask a question, mid-lesson |
| **⌄ dev** | the §41 panel: pipeline, fallback reason, retries, latency, checkpoint, event stream |
| **🔊** chip / volume slider | per-tab mute + output level |
| **🗣** voice chip | which engine voices the tutor: **browser voice** (default in the demo) → **service PCM** → **both** |

### How it explains — grounded, and pitched at the student's level

Picking a topic does not make the tutor improvise. Each of the 22 catalogue
topics carries a **vetted pack** in `app/learning/sources.py`: the sources this
service chose for it (MIT OpenCourseWare, Khan Academy, OpenStax, official docs
— each with a `why`), the facts it is allowed to teach, a picture for it, a
worked example, the mistake students actually make, and the closing question.
From that pack and the student's level, `app/learning/explainer.py` builds the
**explanation brief**: the order the explanation takes, the sentence length it
is allowed, how many mistakes to raise, and what kind of question to end on.

**And a question gets the point that answers it.** The brief carries the whole
vetted pack as an `answer_pool`, not just the slice a level teaches; the student's
words are stemmed (Arabic and English prefixes stripped) and matched against it, so
*"إيه الفرق بينه وبين البحث العادي؟"* is answered with the pack's own comparison with a
one-by-one search. Relevance outranks variety: if the answering point was already
made, it comes back. Then teaching resumes from the next part with something new in
it — never from the start, never skipping what was not taught.

**And a turn is a teaching pass, not one line.** The brief is turned into
*passes* by `app/learning/lesson_script.py`: one pass per lesson section, several
sentences that develop it (a beginner gets 3–5, an advanced student 4–7), the
worked example, the mistake, and a bridge into the next part. The tutor says a few
words of acknowledgement and keeps teaching; it answers a question from the vetted
material and then carries on; it re-teaches a part by another route when the
student is lost; and it never says the same sentence twice. `INTERACTION_SUFFIX`
tells live models the same thing, so this holds whether the voice is the offline
tutor or a real one.

| Level | How it is explained |
|---|---|
| beginner | picture first, one idea at a time, short clauses, closed check-in |
| intermediate | the idea, a worked example, why it works, one common mistake |
| advanced | the mechanism and its cost, two failure modes, an open question |

The level is the student's, not a guess: it is read from their LERNA Progress
Profile (`level`), with a local mirror in the meantime
(`LEARNER_PROFILE_PATH`, `demo-data/learner_profiles.json`), and a request may
override it (`{"level": "advanced"}` on session create, or
`POST /voice/session/{id}/level` mid-lesson — concepts, checkpoint and questions
are untouched). What comes back is visible to the client: the state endpoint
carries the whole brief and the socket emits `explanation.planned`. Live models
receive it as an instruction block ("every factual claim must come from the facts
above — if something is not covered, say you would have to check the course
material"); the offline demo receives the same brief and teaches from it, so the
level is audible without a vendor key. See `docs/EXPLANATIONS.md`.

### What the tutor can teach

`/topics` is the entry point: five courses, 22 topics and 88 lesson steps
(Algorithms, Calculus, Mechanics, Python, Cell Biology). Pick a topic and one of
the **ten languages**, and the tutor teaches that topic's sections in order —
Igbo included, which composes `cascade:elevenlabs+gemini+gemini` while the other
nine route natively through Gemini Live. Every topic also has a vetted pack
(22/22) that the explanation is built from — 11 of them translated to fusHa — and
`/topics` lets you choose the level to explain for, so the same lesson can be
heard three ways. The same catalogue is available over
REST (`GET /curriculum/courses`) and is passed to the model as the lesson plan,
so checkpoints name real lesson steps and a resume continues from the step the
student was on. See `docs/CURRICULUM.md`.

### Hearing a clear voice

The service streams PCM16 and, with real vendor keys, that *is* the tutor's
voice. The offline demo runs on mock vendors, whose audio is deliberately
synthetic — audible, but a buzz rather than speech. So the demo page can voice
the assistant transcript with the browser's own speech synthesiser instead:

- **browser voice** (demo default) — each sentence is spoken the moment it
  completes, using the best voice installed for the session language (the
  standard Arabic voice, `ar-SA`, ahead of a dialect one), so the answer starts
  immediately. Nothing to install; no network.
- **service PCM** is the *humanised* path whenever a vendor key is present:
  Azure AI Speech, with `mstts:express-as style="cheerful"`, a small pitch lift,
  breaths at sentence and clause boundaries and emphasis on English terms.
- **service PCM** — plays what the service sent. Use this to inspect the vendor
  audio path itself, and watch `Received` in the dev panel climb.
- **both** — for comparing the two side by side.

Cycle with the **🗣** chip; the dev panel shows the engine, the installed voice
count, sentences spoken, and a voice picker. `assistant.interrupted` silences
both engines on the same tick (§23), and PCM bytes are counted even when the
browser is the one speaking, so the diagnostics never lie about what arrived.

Run against the real vendors (clear neural voices, no mock) by supplying keys:

```bash
cp .env.example .env      # add AZURE_SPEECH_KEY + AZURE_SPEECH_REGION / GEMINI_API_KEY / …
uvicorn app.main:app --port 3000    # VOICE_ENABLE_MOCK_PROVIDERS left unset
```

Docker:

```bash
docker build -t lerna-voice-ai .
docker run --env-file .env -p 8080:8080 lerna-voice-ai
```

Tests (no credentials needed):

```bash
pytest -q                       # 395 tests
pytest tests/provider -q        # failover matrix
pytest tests/e2e -q             # full §55 scenario
```

---

## Architecture in one picture

```
 browser / mobile client
        │  WS: binary PCM16 in · JSON events out
        ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI  app/main.py                                        │
│   api/routes.py · api/websocket.py · api/security.py         │
├──────────────────────────────────────────────────────────────┤
│  VoiceSession  (app/voice/session_manager.py)                │
│   state · checkpoints · interruptions · resume · latency     │
├───────────────┬──────────────────────────────────────────────┤
│ ProviderRouter│  capability registry + health + circuit br.  │
├───────────────┴──────────────────────────────────────────────┤
│  realtime: Gemini Live                                       │
│  cascade :  STT ──► LLM ──► TTS   (vendors mixed freely)     │
│             EL/DG   Gemini/LERNA   Gemini/EL/DG              │
├──────────────────────────────────────────────────────────────┤
│  LernaBridge → RAG · Progress Profile · Orchestrator         │
│  MongoDB (sessions, checkpoints, questions, provider events) │
└──────────────────────────────────────────────────────────────┘
```

---

## Provider strategy (short version)

* **Gemini Live** is the primary engine for 9 of the 10 languages — one socket does
  STT + reasoning + TTS with native barge-in.
* **Igbo has no Gemini Live support**, so it runs as a *composed pipeline*:
  ElevenLabs Scribe v2 Realtime (STT) → Gemini (LLM) → Gemini Flash TTS (voice).
  No language was dropped and nothing is machine-translated through English.
* If Gemini fails, the router builds a cascade from whatever healthy components
  cover the language; **LERNA's own model pool** can serve the LLM slot so a
  total Gemini outage still leaves a working tutor.
* Deepgram is the third tier and is honestly narrow: STT for `en/ar/fr`, TTS for
  `en/fr` only.

Full matrix: [`docs/LANGUAGES.md`](docs/LANGUAGES.md) · [`docs/PROVIDERS.md`](docs/PROVIDERS.md) · [`docs/FAILOVER.md`](docs/FAILOVER.md)

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/VOICE_TUTOR.md`](docs/VOICE_TUTOR.md) | How the tutor works: turns, checkpoints, interruptions, resume, privacy. |
| [`docs/API.md`](docs/API.md) | REST endpoints, payloads, auth, error codes. |
| [`docs/WEBSOCKET_PROTOCOL.md`](docs/WEBSOCKET_PROTOCOL.md) | Frame types, control messages, every server event. |
| [`docs/PROVIDERS.md`](docs/PROVIDERS.md) | Vendor capabilities, models, wire contracts, adding a provider. |
| [`docs/FAILOVER.md`](docs/FAILOVER.md) | Health, circuit breaker, retry policy, failover matrix, continuity guarantees. |
| [`docs/LANGUAGES.md`](docs/LANGUAGES.md) | Per-language verified support and pipeline choice. |
| [`docs/EXPLANATIONS.md`](docs/EXPLANATIONS.md) | The grounded, level-adapted explanation layer: sources, levels, the brief, **the teaching pass (what a turn is)**, the profile. |
| [`docs/RAG_INTEGRATION.md`](docs/RAG_INTEGRATION.md) | How retrieval is reused, not rebuilt. |
| [`docs/PROGRESS_PROFILE.md`](docs/PROGRESS_PROFILE.md) | Learning signals written back to LERNA. |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Env vars, Docker, scaling, health checks, secrets. |
| [`docs/TESTING.md`](docs/TESTING.md) | Suites, mock providers, how to extend. |
| [`docs/BACKEND_HANDOFF.md`](docs/BACKEND_HANDOFF.md) | Exact contract for the LERNA backend/frontend teams. |

---

## Configuration essentials

| Variable | Meaning |
|---|---|
| `VOICE_PROVIDER_MODE` | `auto` (default) · `gemini_only` · `elevenlabs_only` · `deepgram_only` |
| `VOICE_SERVICE_API_KEY` | Shared secret for service-to-service calls |
| `GEMINI_API_KEY` *or* `GOOGLE_GENAI_USE_VERTEXAI=true` + `GOOGLE_CLOUD_PROJECT` | Two supported Gemini auth paths, auto-detected |
| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | The demo's humanised voice (free F0 tier, 0.5M chars/month) |
| `ELEVENLABS_API_KEY`, `DEEPGRAM_API_KEY` | Backup vendors |
| `MONGODB_URI` | Session persistence (falls back to in-memory if unset) |
| `LERNA_INTEGRATION_MODE` | `auto` · `inprocess` · `http` · `disabled` |

All of them, with comments, live in [`.env.example`](.env.example).
**Provider keys never leave the server**; browser clients receive only a
short-lived `vst_*` session token.

---

## Known limitations

Stated plainly, as required by the spec:

1. **Live traffic: voices yes, Gemini Live no.** ElevenLabs v4 (`en/ar/fr` over
   its socket, five more over REST) and Azure AI Speech (all seven of its
   languages) have been run against live keys and their PCM inspected. The
   Gemini Live socket is written against the documented protocol but has never
   completed a turn — the Google project is billing-blocked (error 1008/403).
   The automated suite itself still runs entirely on mock providers.
2. **Igbo is cascade-only** (~600–1200 ms expected turn latency vs ~300–600 ms
   for native Gemini Live) and currently depends on a *single* STT vendor
   (ElevenLabs) — a real single point of failure.
3. **Yoruba has a single TTS vendor** (Gemini Flash TTS). ElevenLabs v4 does not
   cover Yoruba or Igbo.
4. **Deepgram is not a full backup** — no TTS outside `en/fr`, no STT outside
   `en/ar/fr`. For the other seven languages the real resilience story is
   Gemini ↔ ElevenLabs (+ LERNA's LLM pool).
5. **The LERNA LLM component is not token-streaming.** The existing engine
   returns a complete answer, which is then chunked into sentences; audio still
   streams sentence by sentence.
6. **Single-process session affinity.** Sessions live in memory in the worker
   that owns the socket; horizontal scaling needs sticky routing.
7. **The level mirror is local until the profile integration is switched
   on.** The level is read from LERNA's Progress Profile when it answers, and
   otherwise from `demo-data/learner_profiles.json`; precedence already prefers
   LERNA's value, and nothing else in the service needs to change when that
   integration goes live. The vetted packs cover the demo catalogue (22/22); a
   production deployment generates them from LERNA's own material
   (`docs/CURRICULUM.md`).
8. **Azure covers 7 of the 10 languages.** Its neural catalogue (like the
   browser's *Natural* voices, which are the same Microsoft voices) has no
   Hausa, Yoruba or Igbo; those three speak through Gemini/composed pipelines.
   The free F0 tier also caps at 1 concurrent request and 20 requests/60 s.
8. **Streamlit harness cannot stream a microphone.** It drives the same API with
   text turns and plays back returned audio; it is a developer tool only.
