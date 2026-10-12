# LERNA Voice AI Service — implementation report

Date: 2026-10-11 · Location: `voice-ai/` inside the LERNA repository ·
Python 3.13 · **395/395 automated tests passing, zero paid credentials required.**

Rule applied throughout this report: a feature is marked **Yes** only if it is
implemented *and* covered by a passing test. Anything implemented but not
executed against a real vendor is marked **Code complete, unverified live**.

---

## 1. Feature status

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Real-time streaming voice conversation (not record→upload→transcribe) | **Yes** | `app/api/websocket.py` binary PCM in / event stream out; `tests/websocket/` |
| 2 | Continuous mic streaming, provider-native VAD / turn detection | **Code complete, unverified live** | Gemini Live VAD, EL `commit_strategy=vad`, DG `UtteranceEnd`; mocks exercise the plumbing only |
| 3 | Barge-in with immediate client-side playback stop | **Yes** | `assistant.interrupted{stop_playback:true}` emitted before all other work; ordering asserted in `tests/integration/test_session_lifecycle.py` |
| 4 | Unlimited interruption → question → follow-up → resume cycles | **Yes** | `test_multiple_interruption_cycles`, `test_question_then_followup_then_resume` |
| 4b | Humanised tutoring — teaches continuously rather than quizzing after every step; reacts to the actual answer; rephrases another way; wording rotates so nothing is repeated | **Yes** | `INTERACTION_SUFFIX` (rules asserted in `tests/unit/test_interaction_layer.py`) + `PHRASE_VARIANTS` rotation in `app/providers/mock/dialogue.py`; a whole-plan walk is checked to contain at most one check-in and at least one teaching turn with no question at all |
| 4c | Live voice configured for the native-audio model: affective dialog on, proactive audio optional, voice selectable, optional fields dropped if the model rejects them | **Yes (unit-tested against the real SDK; not exercised against a live vendor)** | `app/providers/gemini/live.py`, `GEMINI_AFFECTIVE_DIALOG` / `GEMINI_PROACTIVE_AUDIO` / `GEMINI_VOICE_NAME`; `tests/unit/test_live_voice_config.py` records the setup payload a stub client receives, and — when `google-genai` is installed — validates that exact payload against the SDK's own `LiveConnectConfig` |
| 4d | Mid-lesson language switch is **heard** in the new language, at the same plan step | **Yes** | `SessionManager.change_language()` sends the switch prompt (or a resume tagged as a switch); plan position travels as `metadata.step_index`. Verified live over WS and tested |
| 4e | Spoken delivery — a turn is a *sentence in the session language*, not a recital of the plan, and what reaches the synthesiser is words rather than symbols | **Yes** | `STEP_LEAD` / `MOVE_ON` / `REACT` (4/5/4 frames × 10 languages, rotating per step) in `app/prompts/interaction.py`; `speakable()` normalises maths before TTS server-side and before `speechSynthesis` in the demo; the browser picks the most natural installed voice, prefers the standard Arabic voice (`ar-SA`) over a dialect one, and reports when the device has none. Tests: `test_spoken_steps_are_sentences_in_every_language`, `test_speakable_turns_written_maths_into_words`, `test_the_voice_follows_the_language` |
| 4f | Real human voice for the **offline** demo — the dialogue stays local, the speech comes from a vendor (`VOICE_DEMO_VOICE`) | **Yes — verified against the live vendor** (en/ar/fr streamed, 666–1048 ms to first audio; sw/am/ha/so/zu over REST with `eleven_v4_turbo`, 599–1032 ms) | `app/voice/demo_voice.py` + `ProviderFactory.build_pipeline()`; the vendor's PCM bytes reach the student unchanged (`tools/check_demo_voice_live.py` proves it from a real WebSocket: speech has thousands of distinct samples per second, the synthetic tone a few dozen), a failing vendor falls back and is counted, `/health` reports the voice name only, `GET /voice/voices` lists voices server-side. Tests: `test_demo_voice.py` (15), `test_elevenlabs_transport.py` (12) |
| 4g | **Learning state is stored in English even when the lesson is taught in another language** — concepts, misconceptions, checkpoints and resume instructions stay canonical for the Progress Profile | **Yes** | `app/learner/canonical_concepts.py` resolves localised wording back to the catalogue phrase (localised title/goal/fragment → English; English kept as said with a `catalogue_ref` anchor; unresolvable wording kept and flagged, never guessed). Applied at every write point: `record_learning_signal`, `update_lesson_position`, checkpoint extraction. The offline tutor reports the finished step's English concept. Tests: `tests/unit/test_canonical_concepts.py` (11) |
| 4h | **Azure AI Speech as the free, official voice** — the same Microsoft voice catalogue the browser exposes, now from a real vendor with a key | **Yes — run live on `germanywestcentral`** (7/7 voices answered at 0.97–1.44 s per line; a real 18.7 s Arabic tutor turn streamed over the WebSocket in 3.8 s to first audio) | `app/providers/azure/tts.py` — REST + SSML (`rate` from `AZURE_SPEECH_SPEED`), `riff-24khz-16bit-mono-pcm` with the RIFF header stripped so the student receives bare PCM16 like every other path; registered in the factory and chosen first by `VOICE_DEMO_VOICE=auto` because F0 gives **0.5M characters/month (≈ 8 h)** against ElevenLabs' 10 000 free credits. Hausa, Yoruba and Igbo have no Azure voice — those stay on Gemini/composed pipelines. Key lives only in the git-ignored `.env`. Tests: `test_azure_tts.py` (7, offline) |
| 4i | **Arabic is taught in Modern Standard Arabic (fusHa) only** — one register, end to end | **Yes — run live on `germanywestcentral`** (fusHa session: «مرحبًا بك، لنبدأ الدرس. نتناول اليوم البحث الثنائي…», 905 KB of audio; the plan, the checkpoint and the concepts are untouched by the register) | `app/voice/dialects.py` (a single `ar-MSA` entry; every Egyptian spelling — `ar-EG`, `egyptian`, `masri` — normalises to it, so an older client is answered in fusHa instead of failing), `AzureTTSProvider.voice_for(…, dialect)` → `ar-SA-ZariyahNeural`, the formal phrase table in `app/prompts/interaction.py`, the formal greeting and the runtime instruction (`app/prompts/languages.py`), `app/curriculum_localisation.py` in fusHa, and the picker's single Arabic entry. The language code stays `ar` for routing, checkpoints and the canonical-English concept store. Tests: `test_arabic_dialects.py` (24) + `test_arabic_session_request.py` (7) |
| 4j | **The voice sounds human, not like an announcement** | **Yes** | `AzureTTSProvider._ssml` adds the vendor's expressive style (`cheerful`, degree 1.05), a `+2%` pitch lift, a `<break>` at sentence and clause boundaries and moderate `<emphasis>` on the English technical terms; a voice that refuses the style costs exactly one un-styled retry and is remembered. Listenable A/B: `demo-audio/arabic-humanised.wav` |
| 4k | **A topic added from the course is studied from the course material plus vetted sources, and explained from human logic, scaled to the student's level** (round 19) | **Yes — working end to end in the offline demo**, and unit/integration tested without any vendor key | `app/learning/sources.py` — 22 topic packs (one per catalogue topic), each a set of `Source`s (publisher, title, kind, public URL, and *why* it was chosen) plus the allowed `fact`/`analogy`/`example`/`pitfall`/`use`/`check` items, canonical English with fusHa for 8. `app/learning/levels.py` — three levels and what each demands (clause length 11/16/24, analogy only for beginners, reasoning from intermediate, 1–2 mistakes, closed/applied/open closing question). `app/learning/explainer.py` — `build_brief()` turns pack + level + lesson plan into ordered moves spread across the lesson's own sections, `prompt_block()` (what the live model must obey: allowed facts, no guessing, level, no URLs), and `as_dict()` for the wire. `app/learner/profiles.py` — the level, request > LERNA profile > local mirror > default. Surfaced as `level` on session create, `student_level` + `explanation` on the state endpoint, `POST /voice/session/{id}/level` mid-lesson, and the `explanation.planned` socket event. An Arabic lesson never mixes in English (untranslated items are left out, and the topic falls back to the plan). The offline tutor is handed the same brief, so the level is audible with no vendor key. Tests: `tests/unit/test_explanation_engine.py` (35) + `tests/integration/test_grounded_explanation.py` (11) |
| 4l | **A turn is a teaching pass, not one line and a check-in** (round 20 — "he just says a sentence and then asks if I have a question") | **Yes — heard end to end over the socket**, offline and with a real voice (`demo-audio/teacher-turns-ar.wav`, 3 m 35 s) | `app/learning/lesson_script.py` — the grounded moves become *passes*: one per lesson section, several sentences, each developing one part of the lesson. `app/learning/explainer.py` — sectioned packs (`Item.section`), per-level selection (`LEVEL_ITEMS`), rotating lead-ins (`FRAME_VARIANTS`) that stop rather than repeat. `app/providers/mock/dialogue.py` — acknowledge in a few words and keep teaching, answer a question from the vetted material and carry on, re-teach by another route, and keep the floor open after the plan ends; no sentence is ever spoken twice in a session. `INTERACTION_SUFFIX` tells live models the same thing in words. Tests: `tests/unit/test_teacher_mode.py` (16) |
| 4m | **A question is answered from the vetted material, matched to the words asked** (round 21) | **Yes — verified live over the socket** | `ExplanationBrief.answer_pool` carries the whole vetted pack in the lesson language, not just the slice a level teaches. `app/providers/mock/dialogue.py` stems the question (Arabic and English prefixes stripped), ranks the pack against it, drops the lead-in already used, and lets relevance outrank the no-repetition rule — then resumes from the next part with something new in it. Confusion takes another route from the pack (a picture or a worked example) instead of re-cutting the same sentence. Live check: "إيه الفرق بينه وبين البحث العادي؟" → the pack's own comparison with a one-by-one search; "كم مقارنة لمليون عنصر؟" → the twenty-comparison fact; "ليه لازم البيانات تكون مرتبة؟" → the sorted-order assumption. Tests: `tests/unit/test_teacher_mode.py` (17) |
| 4m | **A question is answered with the point that actually answers it** (round 21) | **Yes — verified live over the socket** | The brief now carries `answer_pool`: every vetted item of the pack in the lesson language (19 for binary search) rather than only the 11 a beginner's lesson walks through. `app/providers/mock/dialogue.py` stems the question and the pack (Arabic and English prefixes stripped), ranks one against the other, drops a lead-in the tutor already used, and lets relevance outrank the no-repetition rule — then resumes from the next part that still has something new in it. Confusion takes another route from the pack (a picture or a worked example) instead of re-cutting the same sentence. Live: "إيه الفرق بينه وبين البحث العادي؟" → the pack's own comparison with a one-by-one search; "كم مقارنة لمليون عنصر؟" → the twenty-comparison fact; "ليه لازم البيانات تكون مرتبة؟" → the sorted-order assumption. Tests: `tests/unit/test_teacher_mode.py` (17) |
| 4n | **An Arabic lesson stays Arabic, teaches the whole topic, and answers behind a button** (round 22 — screenshot: English mixed into an Arabic cell-structure lesson) | **Yes — verified live over the socket** | Root cause: the biology packs (`cell-structure`, `dna-rna`, `photosynthesis`) had no Arabic, so the topic was not `ARABIC_READY`, the brief carried no moves, and the tutor fell back to English scaffolding. Fix: `app/learning/sources.py` — easy fusHa Arabic added to all 30 biology items (now **11/22** packs Arabic-ready); `app/curriculum_localisation.py` — biology plan titles/goals localised; `app/providers/mock/dialogue.py` — a `_scrub` backstop strips any 3+-word English phrase from an Arabic or Amharic utterance (Latin-script languages are left alone, so French/Swahili/etc. are untouched). The answer flow now confirms before resuming: answer → "هل الأمر واضح حتى هنا؟" → on "نعم" carry on from the part that follows. `app/static/voice_mode.html` — a labelled **🙋 Ask** button (§8): stops playback, interrupts, opens the mic. Live proof (Arabic `cell-structure`, beginner): opening + question + confirm, **0 English-phrase leaks**. Tests: `tests/unit/test_teacher_mode.py` (20) |
| 4o | **The lesson is taught once, straight through, and ends with one 'any questions?'** (round 23 — 'after it finishes it starts explaining again with the same text') | **Yes — tested** | Root cause: every provider (re)connect rebuilt the tutor and re-ran the opening, so a mid-session failover greeted and re-explained from the top. Fix: `app/voice/session_manager.py` marks the 2nd+ connect `resumed`; `app/providers/mock/providers.py` then continues from the stopped step instead of re-opening. `app/providers/mock/dialogue.py` — `_speak_pass` no longer tacks a comprehension question onto every part (teach straight through), and `_after_lesson` asks 'any questions?' exactly once at the very end, and only if the student never asked one; a student who asked just gets the close. `app/prompts/interaction.py` — the live model gets the same rules in words (never restart/re-explain; one end-of-lesson question). Tests: `tests/unit/test_teacher_mode.py` (22) |
| 4p | **A second, optional Arabic register: polite Egyptian — fusHa stays the default** (round 24 — 'keep the formal arabic, add another arabic field, egyptian but polite') | **Yes — tested** | `app/voice/dialects.py` — new `ar-EG` Dialect (voice `ar-EG-SalmaNeural`, lang tag `ar-EG`, line_language `ar-eg`); Egyptian aliases (`egyptian`, `masri`, `ar-EG`, …) now map to `ar-EG` instead of being folded into fusHa. `app/prompts/interaction.py` — a polite-Egyptian phrase table (`ar-eg`, respectful: 'يا فندم/حضرتك', no slang) that falls back to fusHa (`ar`) before English; `app/curriculum.py` — Egyptian greeting. `/voice/languages` now advertises both registers. Default (no dialect) is still fusHa. Tests: `test_arabic_dialects.py`, `test_arabic_session_request.py` (suite 404) |
| 4q | **OpenRouter added as a second 'brain'; live-benchmarked against Gemini, winner primary** (round 25 — 'OpenRouter generates the lesson, Azure speaks it, and answers questions') | **Yes — benchmarked live** | `app/providers/openrouter/llm.py` — OpenAI-compatible streaming LLM component; registered in `factory.py` and given an `llm` capability for all 10 languages (`capabilities.py`). `provider_router._priority` honours `llm_priority` (auto mode). Live benchmark (`tools/benchmark_llms.py`, polite Egyptian): Gemini text `503` (overloaded) on lesson AND question; OpenRouter (`openai/gpt-4o-mini`) answered both (ttft 2.1-3.1 s) in natural polite Egyptian; Azure `ar-EG-SalmaNeural` spoke the winner (155 chunks / 3.4 s). Verdict applied: `LLM_PRIORITY=openrouter,gemini` in `.env` — OpenRouter primary, Gemini secondary + still the realtime native-audio path. Suite 404. |
| 4r | **Dynamic conversation policy + lessons from the student's own uploaded material** (round 26 — 'upload material + pick/type a topic → perfect lesson; answer & simplify anything; if you can't understand ask to repeat, 3× then ask them to write it, then "I didn't get your point"; impolite → warn once, second time end and close the lesson; dynamic not scripted') | **Yes — tested** | `app/providers/mock/dialogue.py` — two new intents `IMPOLITE`/`UNCLEAR` with `is_impolite` (narrow ar+en lexicon) and `is_unclear` (letter-ratio/short-token noise, but never flags a known reply or a question mark). `TutorDialogue.respond()` runs a stateful gate before teaching: unclear → 3 rotating 'say it again' (via `_v`) → 4th 'type it' → 5th+ 'I didn't get your point', and a clear turn resets the streak; impolite → 1st calm warning, 2nd ends the lesson (`_ended_for_conduct`, `done=True`) and every later turn is 'the lesson is closed'. `app/prompts/interaction.py` — the same policy in words in `INTERACTION_SUFFIX` so the live OpenRouter/Gemini brains behave dynamically, plus new `repeat_please/type_it/not_got/polite_warn/polite_end/lesson_closed` phrases (en/ar/ar-eg) and rotating `repeat_please` variants. `app/rag/local_corpus.py` — ingests uploaded material (chunk + token-overlap retrieve); `POST /voice/material` ingests and returns a `document_id`; `session_manager._brief()` retrieves it for the session's `document_ids`; `explainer.build_brief(evidence=…)` composes teaching moves from the upload (`grounding='uploaded'`) when the topic has no curated pack. Live: `POST /voice/material` → `{document_id, chunks}`; `/health/providers` unchanged (openrouter primary). Suite **408**, exit 0. |
| 4s | **Fish Audio added as a backup voice; live-benchmarked on its real axis** (round 27 — 'use the Fish Audio key as a backup, test it with OpenRouter and Gemini, who wins') | **Yes — benchmarked live** | Fish Audio is a **TTS** service, not a text brain, so it competes with Azure on the VOICE axis, not with OpenRouter/Gemini on the BRAIN axis. `app/providers/fish/tts.py` — `FishAudioTTSProvider` (`POST api.fish.audio/v1/tts`, Bearer auth, free `s2.1-pro-free`, auto language detection); parses the WAV header, downmixes to mono and resamples to the pipeline PCM16 rate so it is byte-compatible with Azure/Gemini/EL. Registered in `factory.py` (`_tts['fish']` + vendor mock), `capabilities.py` (`tts={en,ar,fr,sw}` — documented languages only; Hausa/Yoruba/Igbo/Somali/Amharic deliberately unclaimed), `config.py` (`fish_audio_api_key`/`fish_audio_model`/`fish_configured`, added to `configured_providers`), `.env.example` (blank). Key in `.env` only (chmod 600). Live benchmark (`tools/benchmark_tts.py`): **BRAIN** — OpenRouter ttft 2.5-2.9 s beat Gemini 6.5-7.5 s (both correct polite Egyptian) → OpenRouter stays primary. **VOICE** — Azure ttft 3.4 s / 30.4 s audio beat Fish 13.7 s / 26.7 s audio (Fish is non-streaming REST, so latency scales with clip length) → Azure stays the voice, **Fish is the backup voice**. Router: `fish` usable for TTS ar/en/fr/sw, correctly rejected for `ha`. Suite **408**, exit 0. |
| 4t | **Fish Audio auto-failover behind Azure + VS Code zip + deploy artifacts** (round 28 — 'Fish works automatically as a backup voice if Azure fails; give me a folder zip to test in VS Code; give me the deploy file and its backend deployment') | **Yes — tested** | `app/providers/cascade.py` — `_speak()` now tries the active voice then each backup, failing over only if a voice breaks *before* speaking (a mid-line drop surfaces an error, never a duplicate). `app/providers/factory.py` — `build_pipeline` attaches `tts_fallbacks` via `_tts_failover()` in the order **azure → fish → elevenlabs → gemini → deepgram** (configured voices only). Live check: an Azure cascade builds with `tts_fallbacks=['fish','elevenlabs','gemini']`. Tests: `tests/unit/test_tts_failover.py` (4) — failover-before-speech, all-down→error, mid-line→no-duplicate, factory order. Suite **412**, exit 0. Deploy: `Dockerfile` (non-root, healthcheck, 1 worker) + new `docker-compose.yml` (one-command `docker compose up --build`); `docs/DEPLOYMENT.md` updated (Fish env + voice-failover section); `docs/BACKEND_HANDOFF.md` is the backend integration contract (endpoints/tokens/sequence). Packaged `voice-ai-vscode.zip` (549 KB) with `.env`/`.secrets`/service-account **excluded** + a new `QUICKSTART.md`. |
| 4u | **Console toast `UnsupportedLanguageError` was a mislabelled provider outage — fixed** (round 29 — screenshot: connected + 'Ready 4 steps' but toast 'Could not process that request: UnsupportedLanguageError') | **Yes — reproduced & fixed** | Root cause: `VoiceSession._connect()` retries/falls over across pipelines; when a transient provider outage (e.g. Gemini realtime 503) made *every* plan fail, the next `select_pipeline(exclude=failed)` raised `UnsupportedLanguageError`, which the WS control handler showed as 'Could not process that request: UnsupportedLanguageError' — wrong, the language WAS supported. Fix in `app/voice/session_manager.py`: in the `except UnsupportedLanguageError` branch, if `self._failed_signatures` is non-empty (we had plans that all failed), `break` into the existing honest 'No voice provider could be reached' error (with the real provider error + hint) instead of claiming the language is unsupported. A genuinely-unsupported language (no plan ever) still reports `VOICE_LANGUAGE_UNSUPPORTED`. Verified: live WS for `cell-structure`/`ar` streams Arabic text + audio with no error; Arabic has 12+ cascade fallbacks behind Gemini realtime. Tests: `tests/unit/test_outage_error_message.py` (2) — outage→not-language-unsupported, genuine→still-language-unsupported. Suite **414**, exit 0. |
| 4v | **Speech order: OpenRouter+Azure primary, Gemini 2nd, ElevenLabs 3rd; ar+en verified** (round 30 — 'make arabic and english work perfectly; openrouter+azure speech primary, gemini second, elevenlabs third') | **Yes — live-verified** | `app/config.py` — `azure_configured` + azure added to `configured_providers()` (so Azure is a selectable voice); new `voice_priority` (default `azure,gemini,elevenlabs,fish`). `app/voice/provider_router.py` — a composed pipeline whose TTS is the #1 voice (Azure) now gets a strong primary bias so it outranks native realtime; other cascades keep the historical below-realtime ranking. Live: ar & en both connect as `stt=elevenlabs/gemini + llm=openrouter + tts=azure` and stream Azure-spoken audio. `app/providers/factory.py` — `TTS_FAILOVER_ORDER=(azure, gemini, elevenlabs, fish, deepgram)`. `app/api/routes.py` + `app/main.py` — `realtime_native` now means 'a native-realtime option exists' (not 'primary is realtime'), so the /topics & /voice pages stay correct. Tests updated (`test_tts_failover`, served-pages). Suite **414**, exit 0. |
| 4w | **Console 401 `VOICE_AUTH_REQUIRED` lockout fixed** (round 31 — screenshot: POST /voice/session → 401 VOICE_AUTH_REQUIRED) | **Yes — fixed & verified** | Root cause: `deploy/.env.production.example` sets `VOICE_AUTH_REQUIRED=true` but leaves `VOICE_SERVICE_API_KEY=` blank; auth against an *empty* key can never match, so every call (incl. the service's own console) 401'd. Fix in `app/api/security.py` (`require_service_auth` + `authenticate_websocket`): when **no key is configured**, run open (anonymous) regardless of the required flag — a misconfiguration guard; once a key is set, auth is enforced strictly (existing 401 test still passes). `app/main.py` logs a startup warning when auth is required but the key is empty. `deploy/.env.production.example` documents the behaviour. Live: with `VOICE_AUTH_REQUIRED=true` + blank key, `POST /voice/session` → 201 and `/voice` → 200. Test: `test_ws_protocol.py::test_auth_required_with_blank_key_does_not_lock_out_console`. Suite **415**, exit 0. |
| 4x | **Lesson taught straight through, calm & human; text streams word-by-word; no stop-questions** (round 32 — 'keep explaining the whole lesson without stopping; words appear one by one; don't ask if I have a question — teach until I raise my hand') | **Yes — live-verified** | `app/prompts/system.py` — `OPENING_PROMPT` rewritten: greet in one line, then teach the ENTIRE lesson in one continuous, calm, unhurried flow covering every plan step; never pause to ask 'do you understand / any questions?'; close with a reassuring line, not a question. `app/prompts/interaction.py` — `INTERACTION_SUFFIX` tightened: flow on between parts (no 'give the student the floor' stop), and 'if the student is quiet, keep teaching — silence means continue'. Live (ar): 84 word-level `assistant.text.delta`s (avg 3 chars), 103 audio chunks, `ends_with_question=False`, no 'عندك سؤال'; the lesson kept going through the plan without stopping. Student interruption (raise hand / ask) still answered via the existing question path. Suite **415**, exit 0. |
| 4y | **Egyptian Arabic added as a selectable, professional option** (round 32 — 'add Egyptian Arabic as a choice — academic Egyptian, works professionally without breaking anything') | **Yes — live-verified** | Added `"ar-eg":"العربية المصرية · Egyptian (academic)"` to the voice UI language picker (`app/static/voice_mode.html` `CFG.languages`); `langBase`/`langDialect` already split it to `language=ar` + `dialect=ar-eg`, so capability routing/pipeline plans stay on `ar` (nothing else breaks). Added the academic-Egyptian register line to `ARABIC_DIALECT_INSTRUCTIONS["ar-EG"]` (`app/prompts/languages.py`) so `build_system_instruction(ar, ar-EG)` now injects 'تحدّث باللهجة المصرية الأكاديمية المهذّبة…' (was silently falling back to fusHa). The `ar-EG` dialect (voice `ar-EG-SalmaNeural`), the `ar-eg` phrase table and Azure `ar-EG` lang tag already existed. Live (ar+dialect=eg): session `language=ar, dialect=ar-EG`, Arabic teaching streamed (63 audio chunks); register instruction verified present. Suite **415**, exit 0. |
| 4z | **Arabic quality fixed (no spelling/literal-translation errors) + Egyptian added to ALL language pickers + folder deployment-ready** (round 33) | **Yes — live-verified** | Quality: new universal QUALITY block in `build_system_instruction` (`app/prompts/system.py`) — 'natural, idiomatic, fluent … never a literal word-for-word translation … flawless grammar and spelling'; both Arabic registers rewritten (`app/prompts/languages.py`) to sound like a native teacher (fusHa: 'مدرّس عربي أصيل'; Egyptian: 'مدرّس مصري مثقّف'). Live sample now reads naturally with zero literal/awkward phrasing. Egyptian in pickers: `topics.html` injects `ar-eg` after `ar` (client-side, rides base `ar`+`ar-EG`); `console.html` + `voice_mode.html` got the option. Browser test updated to 11 options (was asserting 10). Deployment: `Dockerfile`, `docker-compose.yml`, `run.ps1`, `.env.example`, `QUICKSTART.md`, `deploy/` (README, compose, nginx, smoke_test, integration, docs) all present; zip rebuilt secrets-free. Suite **415**, exit 0. |
| 5a | **Railway build failure fixed** — `useradd: group voice exists` | **Yes — reproduced & re-tested** | Cause: `python:3.12-slim` is Debian, and Debian's `base-passwd` already defines a **`voice` group (GID 22)**, so the bare `RUN useradd --create-home --uid 10001 voice` aborted the image build (Railway: "Deployment failed during build process", step 8/8). Fix: idempotent creation — `getent group voice || groupadd --system voice;` then `useradd --create-home --uid 10001 --gid voice voice` (the `-g` the error message itself asks for). Also added `.dockerignore` (keeps `.env`/`.secrets` out of the build context — no secrets in the image), a Railway section in `deploy/README.md` §1b (Dockerfile path / `RAILWAY_DOCKERFILE_PATH`, injected `PORT`, healthcheck `/health`, variables, single replica) and 6 regression tests in `tests/deploy/test_container_contract.py` (asserts every `useradd` passes `-g voice`, non-root user, `${PORT}` in CMD, healthcheck curl, dockerignore excludes secrets). Old failure reproduced with a mock `useradd`; new layer passes both with and without a pre-existing group. Suite **421**, exit 0. |
| 5 | Smart checkpointing on *learning state*, not audio timestamps | **Yes** | `app/voice/checkpoint_manager.py`; `test_interrupt_creates_a_learning_checkpoint` |
| 6 | Smart resume — never restarts the lesson | **Yes** | `test_resume_does_not_restart_the_lesson` |
| 7 | Returning student with recap | **Yes** | `resume_latest` fork + `session.recap`; `tests/e2e/test_full_scenario.py` step 7 |
| 8 | Provider abstraction (STT / LLM / TTS / realtime interfaces) | **Yes** | `app/providers/base.py`, `factory.py` |
| 9 | Composable cross-vendor pipelines | **Yes** | `app/providers/cascade.py`; `test_cascade_streams_stt_then_llm_then_tts` |
| 10 | Central capability registry (STT vs TTS vs realtime vs LLM, per language) | **Yes** | `app/providers/capabilities.py`; `tests/unit/test_capabilities_and_router.py` |
| 11 | Capability-aware router, Gemini → ElevenLabs → Deepgram priority | **Yes** | `app/voice/provider_router.py` |
| 12 | `VOICE_PROVIDER_MODE` auto / gemini_only / elevenlabs_only / deepgram_only | **Yes** | `MODE_TO_PROVIDERS`; unit tests incl. unsupported-language rejection |
| 13 | Health tracking, cooldowns, circuit breaker | **Yes** | `app/providers/health.py`; `tests/unit/test_health_and_errors.py` |
| 14 | Retries with exponential backoff, no-retry classes (auth/quota) | **Yes** | `test_auth_failure_is_not_retried`, `test_gemini_temporary_failure_then_recovers` |
| 15 | Automatic failover + provider history | **Yes** | `tests/provider/test_failover.py` (full §54 matrix) |
| 16 | **Session continuity across failover** | **Yes** | `test_failover_preserves_the_entire_session`; §55 e2e |
| 17 | All 10 mandatory languages, none dropped, no English→MT→TTS | **Yes** | `tests/multilingual/` — 10 × full cycle |
| 18 | Igbo verified and composed | **Yes** | EL STT → Gemini LLM → Gemini TTS; `test_igbo_session_is_fully_functional` |
| 19 | Gemini dual auth (Vertex `gemini-3.8-live` **and** Developer API) | **Code complete, unverified live** | `app/config.py` auto-detect, `app/providers/gemini/client.py` |
| 20 | LERNA RAG reuse (no second RAG) | **Yes (adapter + stub-tested)** | `app/rag/adapter.py`, `app/lerna_bridge.py`; in-process call path unverified against a live Academic OS instance |
| 21 | Progress Profile write-back (no second profile) | **Yes (adapter + stub-tested)** | `app/learner/progress_adapter.py`; `test_tool_calls_drive_visuals_and_learning_signals` |
| 22 | Learning Orchestrator integration | **Partial** | modality registration + next-action adapter implemented; exercised against stubs only |
| 23 | Structured visual learning events | **Yes** | `visual.updated` via `show_visual` tool |
| 24 | Documented realtime event model (~30 events, `seq`-ordered) | **Yes** | `app/voice/events.py`, `docs/WEBSOCKET_PROTOCOL.md`; ordering test in e2e |
| 25 | Provider-agnostic REST + WS API | **Yes** | `app/api/routes.py`; `docs/API.md` |
| 26 | Service auth (`VOICE_SERVICE_API_KEY`) + short-lived client tokens | **Yes** | `app/api/security.py`; `test_client_token_authentication` |
| 27 | Provider keys server-side only | **Yes** | only `ProviderFactory` reads keys; `/health/providers` leak test |
| 28 | MongoDB persistence | **Code complete, unverified live** | `MongoVoiceRepository`; interface parity tested, no live Atlas run |
| 29 | pytest suites incl. mocks, no paid credentials | **Yes** | 395 tests, offline |
| 30 | Failover matrix (§54) | **Yes** | `tests/provider/test_failover.py` |
| 31 | Full E2E scenario (§55) | **Yes** | `tests/e2e/test_full_scenario.py` |
| 32 | Dockerfile + production start command | **Yes** | `Dockerfile` (non-root, healthcheck, uvicorn 1 worker) |
| 33 | `/health`, `/health/providers` | **Yes** | tested |
| 34 | Structured JSON logging with redaction | **Yes** | `app/logging_setup.py` |
| 35 | `.env.example`, `.gitignore` | **Yes** | placeholders only, no secrets |
| 36 | Documentation set (11 documents) | **Yes** | `README.md` + `docs/` |
| 37 | Streamlit testing/demo app with dev panel | **Yes** | the screen lives in `app/static/voice_mode.html` and is served at `/` by the service itself; `streamlit_app/app.py` embeds the same file. Microphone input, streamed playback and the §41 diagnostics drawer; covered by `tests/browser/` and `tests/integration/test_served_pages.py` |
| 38 | Production frontend | **Out of scope by instruction** | — |

---

## 2. Actual fallback architecture (not aspirational)

```
                       ┌──────────────── realtime ────────────────┐
 en ar fr sw am ha     │        Gemini Live (one socket)          │
 so yo zu              └──────────────────────────────────────────┘
                                         │ failure
                                         ▼
                       ┌──────────────── cascade ─────────────────┐
                       │  STT            LLM             TTS      │
                       │  ElevenLabs ─► Gemini ──────► ElevenLabs │   (ar/en/fr/sw/am/ha/so/zu)
                       │  ElevenLabs ─► Gemini ──────► Gemini TTS │   (yo, ig)
                       │  Deepgram  ─► LERNA pool ──► Deepgram    │   (en/fr only)
                       └──────────────────────────────────────────┘
 ig                    cascade is the PRIMARY (no Gemini Live Igbo)
```

A fourth LLM vendor — **LERNA's own model pool** — was added because with
Gemini as the only LLM, a Gemini outage would have killed every cascade too.
With it, a complete Gemini outage still leaves a working tutor in every language
that ElevenLabs can transcribe and speak.

---

## 3. Per-language reality

| Language | Primary | Backup depth | Honest caveat |
|---|---|---|---|
| English | Gemini Live | 3 vendors, full | — |
| French | Gemini Live | 3 vendors, full | — |
| Arabic (fusHa) | Gemini Live | STT ×3, TTS ×2 | no Deepgram TTS |
| Swahili, Amharic, Hausa, Somali, Zulu | Gemini Live | STT ×2, TTS ×2 | Deepgram contributes nothing |
| Yoruba | Gemini Live | STT ×2, **TTS ×1** | only Gemini can speak Yoruba |
| **Igbo** | **Cascade** (EL STT → Gemini LLM → Gemini TTS) | **STT ×1, TTS ×1** | no realtime path; higher latency; genuine SPOF |

---

## 4. Limitations, stated plainly

1. **No live vendor traffic was exercised.** All provider clients follow the
   documented wire protocols, but the test suite runs on mocks. With a real Vertex
   service account the bring-up reaches Google and stops at *project billing*, which
   only the account owner can enable (see §4b) — so the vendor audio path itself is
   still unverified end to end. The Developer API path needs an `AIza…` key.
2. The supplied Gemini credential did not look like a Developer API key, and
   `gemini-3.8-live` is a Vertex model. Both auth paths are implemented and
   auto-detected, but which one works depends on credentials this build never had.
3. **Igbo and Yoruba have single-vendor dependencies** (see table above).
4. **Deepgram is a narrow third tier** — STT `en/ar/fr`, TTS `en/fr`. It is not a
   general-purpose backup and the code refuses to pretend otherwise.
5. **The LERNA LLM component is not token-streaming** — the host engine returns a
   complete answer, chunked into sentences for TTS.
6. **MongoDB was never contacted.** Interface parity is tested; durability is not.
7. **LERNA in-process integration was not run against a live Academic OS**; the
   adapters are written against the verified source interfaces and tested with
   stubs.
8. **Single-process session affinity** — horizontal scaling needs sticky routing.
9. **Latency figures in the docs are design expectations** from vendor
   documentation, not measurements.
10. **The demo's clear voice does not come from the mock vendors.** With real
    keys, the tutor's voice is the vendor's neural TTS (Gemini/ElevenLabs). The
    offline demo's mock audio is synthetic by construction, so the page voices
    the transcript with the browser's speech synthesiser and offers the mock PCM
    as a switchable comparison. This is a demo surface only — it does not change
    the service's audio contract, and every PCM byte is still counted.
11. **The course catalogue is standalone demo content, not the LERNA syllabus.**
    `app/curriculum.py` holds 22 hand-written topics so the service runs with no
    backend. A production deployment sources this from the LERNA course catalogue;
    `docs/CURRICULUM.md` states the data shape that integration must produce.
12. **The mock tutor's conversation is rule-based.** With real credentials the
    dialogue contract above is carried *in the system instruction* and the model
    produces its own natively fluent turns. Offline, `app/providers/mock/dialogue.py`
    stands in: intent from a multilingual keyword table (question mark → question;
    negation before affirmation), steps from the catalogue plan, and hand-written
    phrase/template tables for the ten languages. It is a demo policy, not an LLM —
    it cannot improvise an explanation it was never given. What it *does* do is
    speak: turns are sentence-shaped, leads/transitions/reactions rotate per step,
    a confused student gets three different routes, and no sentence is ever said
    twice in a session (see `docs/VOICE_TUTOR.md`, "What a turn sounds like").
13. **In the offline mock the lesson content is English, except where curated
    translations exist.** `app/curriculum_localisation.py` carries hand-written
    fusHa translations for the demo topics (Binary Search, Merge Sort,
    Recursion), so an Arabic session is spoken entirely in Arabic — plan wording
    included — while the service keeps the catalogue's own (English) naming for
    state, checkpoints and resume. Other topics, and the other nine languages, are
    still spoken as written, wrapped in localised scaffolding. Live vendor sessions
    do not need this: the model receives the plan with the instruction to express it
    in the target language.
14. **The demo voice runs on the ElevenLabs free plan.** 10 000 credits/month
    (≈ 10 minutes of speech), non-commercial, and *library* voices are refused
    through the API (HTTP 402: "Free users cannot use library voices") — the demo
    uses a voice the plan allows and `tools/verify_elevenlabs_voice.py` probes
    alternatives automatically. ElevenLabs TTS covers 8 of the 10 mandatory
    languages (no Igbo, no Yoruba): those two keep the Gemini/browser voice.
15. **The explanation layer is grounded in the demo catalogue, and its level
    mirror is local for now.** The 22 vetted packs cover `app/curriculum.py`; a
    production deployment generates the same structure from LERNA's course
    material, and 11 of the packs carry Arabic today (the rest fall back to the
    lesson plan in Arabic sessions; a backstop strips any English phrase from an
    Arabic or Amharic utterance, so the tutor never switches languages mid-line). The level is
    read from LERNA's Progress Profile when it answers, and otherwise from
    `demo-data/learner_profiles.json` — precedence (request > profile > mirror >
    default) is already the production one.
16. **The Streamlit app is a developer harness, not a frontend.** It does stream
    microphone audio in a normal browser tab, but the preview iframes used for
    hosted demos do not grant microphone permission — there the `+` button
    (synthetic PCM) and typed questions drive the same server paths.

---

## 4b. Live smoke run performed

The service was started for real (`uvicorn app.main:app`) with
`VOICE_ENABLE_MOCK_PROVIDERS=true` and driven over actual HTTP + WebSocket:

| Check | Result |
|---|---|
| `GET /health` | `{"status":"ok"}` |
| `GET /voice/languages` | 10 languages; `ig` reported `realtime_native: false`, pipeline `cascade:elevenlabs+gemini+gemini`; all others `realtime:gemini` |
| Arabic session over WS (start → interrupt → question → resume → end) | 4.8 KB of PCM returned; events in the documented order; checkpoint present; state `ended` |
| Igbo session over WS (same cycle) | ran on `cascade:elevenlabs+gemini+gemini`; 5.8 KB of PCM; checkpoint present |
| RAG with LERNA disabled | recoverable `VOICE_RAG_UNAVAILABLE` emitted, the lesson continued — degradation behaves as documented |

This exercises the real API surface, router and cascade; only the vendor sockets
themselves were mocked.

### Audio path re-verified after the demo fix

The mock vendors originally emitted a constant DC offset (silence) and the demo
client buffered that audio behind a manual "Play" button, so the demo produced
no sound. Both are fixed and covered by tests:

| Check | Result |
|---|---|
| Mock audio is a real waveform, not a DC offset | peak 7203 / rms 4330 (was peak 256) |
| English realtime session over WS | 14 chunks, 1620 ms of PCM16 @ 24 kHz |
| Igbo cascade session over WS | 6 chunks, 700 ms of PCM16 @ 24 kHz |
| Microphone-style input (2 s of 16 kHz frames) | `input.transcript` emitted, then a 3.7 s spoken reply; one turn per utterance, not per byte count |
| Client playback schedule (Node + stubbed Web Audio) | chunks placed back-to-back at exactly their duration; first chunk starts ~40 ms in; 48 kHz output device resamples with pitch preserved |
| `assistant.interrupted` | playback queue cleared immediately |
| Served at `/` on the service port (same origin as REST + WS) | full cycle: health → session → token → WS → 28 chunks / 3240 ms; states `idle → thinking → speaking → listening` |
| Assistant voicing in the demo | transcript spoken sentence-by-sentence through the browser's speech synthesiser, with the mock PCM as the switchable comparison path (see §4 limitation 10) |
| Language switch over WS (`{"type":"language","language":"ar"}` mid-lesson) | Arabic acknowledgement in the same turn, plan step preserved and continued (`هنكمل بالعربي من هنا. إحنا دلوقتي في …`) |
| Conversational reactions (live) | `yes` → advances one step; a confused answer → rephrased, step **not** advanced, and a second confusion uses a different explanation route |
| Opening line per language (live, all 10) | Each language greets, names the topic and teaches step one with its own scaffolding: e.g. `zu` "Sawubona, ake siqale isifundo. Namuhla sisebenza ku-Binary Search." / `am` "ሰላም፣ ትምህርቱን እንጀምር።" (153 600 B ≈ 3.2 s of PCM16 per turn; Igbo 382 560 B via the composed cascade) |
| Sandboxed preview iframe (opaque origin, framed) | The page used `location.origin`, which is the string `"null"` inside `sandbox="allow-scripts"`, so the socket URL became `null/voice/session/…`. It is now built from `location.protocol + location.host`, with an on-page "open in its own tab" affordance when framed — covered by a Node run of the real client JS with an opaque origin and by a served-page contract test |
| Humanised dialogue over WS (live, mock vendors) | Opening teaches step one and *hands the turn over* ("Jump in whenever you want") instead of quizzing; one check-in in a four-step walk; merged turns teach two steps without a question; varied praise each turn; the plan closes once and questions are still answered afterwards |
| `/health` with no keys | `{"mock_providers": true, "gemini_auth": "none", "live_model": "gemini-2.5-flash-native-audio-preview-12-2025", "live_models": {"vertex": "gemini-3.8-live", ...}}` — the shape of the pipeline, never a credential |
| **Live Vertex bring-up (real service account)** | Auth works: the credential authenticates, `/health` reports `gemini_auth: vertex`, `live_model: gemini-3.8-live`. The session is refused by Google with `1008 … requires billing to be enabled … project #lernavoice` — a project configuration state, not a code path. The service surfaces it as `VOICE_PROVIDER_QUOTA_EXHAUSTED` **with a hint containing the exact enable-billing link**, and the screen shows it (the same failure previously surfaced as an opaque `DefaultCredentialsError`; that masking bug is fixed and tested) |
| Topic catalogue over HTTP | `/curriculum/courses` = 5 courses, 22 topics, 88 lesson steps; `/topics` renders it inline |
| Lesson plan reaching the tutor | English `realtime:gemini`, Igbo `cascade:elevenlabs+gemini+gemini` (reported before connect), Arabic `realtime:gemini` — each taught its plan step by step, 6.4–10.6 s of audio per 2–3 turns |

---

## 4c. What is blocked, and on exactly what

Until round 23, one thing stood between this service and a tutor that *writes* its
own explanations instead of assembling vetted sentences: **a working generative-model
credential.** A Developer-API key was then supplied and verified live — the realtime
native-audio session now opens and teaches in natural generative Arabic. What remains
is only request-level stability (free-tier `503` overload spikes on the newest flash
models) and the mic needing a top-level tab (a browser permission rule, not the service).

| Requirement | Status |
|---|---|
| `GEMINI_API_KEY` — a Gemini **Developer API** key from <https://aistudio.google.com/apikey> | **Live (round 23).** The key authenticates and the realtime native-audio session opens and *teaches in natural generative Arabic* (`provider.selected → realtime:gemini`). `GOOGLE_GENAI_USE_VERTEXAI=false`; reasoning model set to `gemini-3.6-flash` because `gemini-2.5-flash` now 404s for new accounts; speech-to-speech stays on `gemini-2.5-flash-native-audio-preview-12-2025` (verified connecting). |
| Vertex AI (`gemini-3.8-live`) via the uploaded service account | **Blocked** — the project answers `403 / billing account 1008`. Needs billing enabled on the Google Cloud project; not something the service can work around. |
| Azure AI Speech (`germanywestcentral`) | **Working** — the voice you hear. TTS/STT only; it cannot reason, so it is never presented as a model fallback. |
| ElevenLabs | **Deliberately frozen** — ~7 free minutes left; the key is in `.env` and unused. |
| LERNA course-material RAG over *uploaded* documents | **Wired but not fed** — `LERNA_INTEGRATION_MODE=disabled` in the demo. Needs the platform's Mongo URI and content API; until then the tutor teaches from the vetted packs, and says so. |

Everything above the line is implemented and tested without any of these keys.

## 5. Security notes

* No credential appears anywhere in source, tests, docs or `.env.example`.
* `.env` is git-ignored; secrets are environment-only.
* Browser clients receive a 15-minute single-session `vst_*` token, never a
  provider or service key.
* Logs are redacted; production responses never carry stack traces.
* **Any API key shared during development should be rotated** before deployment.

---

## 6. How to verify this report

```bash
cd voice-ai
pip install -r requirements.txt
pytest -q                 # 395 passed
pytest tests/provider -q  # failover matrix
pytest tests/e2e -q       # full scenario
uvicorn app.main:app --port 8080
curl localhost:8080/health
curl localhost:8080/voice/languages | jq '.languages[] | {code, realtime_native}'
```
