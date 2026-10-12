# Languages

Ten mandatory languages. None was dropped, and none is served by
English → machine-translation → TTS. Where a vendor cannot do a job, the router
*composes* a pipeline from vendors that can.

## Verified capability matrix

Sources: Gemini Live API capabilities page, ElevenLabs model/STT pages,
Deepgram model & TTS pages (checked while building this service).

| Code | Language | Gemini Live (realtime) | Gemini TTS | ElevenLabs STT (Scribe v2 RT) | ElevenLabs TTS (v4) | Deepgram STT (Nova-3) | Deepgram TTS (Aura-2) |
|---|---|---|---|---|---|---|---|
| `en` | English | ✅ | ✅ | ✅ excellent | ✅ | ✅ | ✅ |
| `ar` | Arabic — taught in Modern Standard Arabic (fusHa) | ✅ | ✅ | ✅ good | ✅ | ✅ | ❌ |
| `fr` | French | ✅ | ✅ | ✅ excellent | ✅ | ✅ | ✅ |
| `sw` | Swahili | ✅ | ✅ | ✅ high | ✅ | ❌ | ❌ |
| `am` | Amharic | ✅ | ✅ | ✅ moderate | ✅ | ❌ | ❌ |
| `ha` | Hausa | ✅ | ✅ | ✅ good | ✅ | ❌ | ❌ |
| `so` | Somali | ✅ | ✅ | ✅ moderate | ✅ | ❌ | ❌ |
| `yo` | Yoruba | ✅ | ✅ | ✅ moderate | ❌ | ❌ | ❌ |
| `ig` | **Igbo** | ❌ | ✅ | ✅ moderate | ❌ | ❌ | ❌ |
| `zu` | Zulu | ✅ | ✅ | ✅ moderate | ✅ | ❌ | ❌ |

Gemini text LLM covers all ten. LERNA's own model pool is registered as a
fourth LLM vendor and also covers all ten.

## Arabic is taught in fusHa

The language code is `ar` everywhere it matters — capability matrix, pipeline
plans, checkpoints, Progress Profile signals, the canonical-English concept store.
Modern Standard Arabic is the only register (`app/voice/dialects.py`):

| Register | Vendor voice | Phrase set | Instruction |
|---|---|---|---|
| `ar-MSA` | `ar-SA-ZariyahNeural` | fusHa (`ar`) | "speak clear Modern Standard Arabic, a simplified lecture voice" |

The demo's picker offers Arabic once (`العربية الفصحى · Arabic (fusHa)`), and the
class-level `dialect` field is still on the session and on `POST
/voice/session/{id}/language` for clients that were written against the earlier
two-register API: every Egyptian spelling — `ar-EG`, `egyptian`, `masri`, `عامية`
— resolves to `ar-MSA`, so an older client is answered in fusHa instead of
failing the lesson. `language.changed` reports `to: "ar"` with
`dialect: "ar-MSA"`.

## Resulting pipelines

| Language | Primary | Fallback 2 | Fallback 3 |
|---|---|---|---|
| `en`, `fr` | Gemini Live (realtime) | EL STT → Gemini LLM → EL TTS | DG STT → LERNA LLM → DG TTS |
| `ar` | Gemini Live | EL STT → Gemini LLM → EL TTS | DG STT → LERNA LLM → Gemini TTS |
| `sw`, `am`, `ha`, `so`, `zu` | Gemini Live | EL STT → Gemini LLM → EL TTS | EL STT → LERNA LLM → Gemini TTS |
| `yo` | Gemini Live | EL STT → Gemini LLM → **Gemini TTS** | EL STT → LERNA LLM → Gemini TTS |
| `ig` | **EL STT → Gemini LLM → Gemini TTS** (cascade) | EL STT → LERNA LLM → Gemini TTS | — |

The router derives these generically by scoring capability coverage and vendor
priority; nothing above is hardcoded per language. Verify at runtime with
`GET /voice/languages`.

## Igbo — the honest version

Igbo is **not** in the Gemini Live language list, so there is no native
speech-to-speech path. Instead of degrading Igbo to text-only, the service
composes:

```
ElevenLabs Scribe v2 Realtime (ibo)  →  Gemini LLM  →  Gemini Flash TTS (ig)
```

Consequences a product owner should know:

* Expected turn latency ~600–1200 ms, versus ~300–600 ms for native Gemini Live.
* Barge-in still works, but it is implemented by cancelling LLM generation and
  TTS playback rather than by a native realtime interrupt.
* **Single STT vendor.** If ElevenLabs is down, Igbo speech input has no backup.
  This is a genuine single point of failure, not a hidden one.

## Other single points of failure

| Language | Risk |
|---|---|
| `yo` | Only Gemini can produce Yoruba speech (ElevenLabs v4 has no Yoruba voice). |
| `ig` | Only ElevenLabs can transcribe Igbo; only Gemini can speak it. |
| `sw`, `am`, `ha`, `so`, `zu` | Deepgram covers none of them — resilience is Gemini ↔ ElevenLabs only. |

## Language behaviour rules

* The tutor answers in the session language. Prompts per language live in
  `app/prompts/languages.py` and explicitly forbid drifting back to English.
* The Arabic **register** is a session property (`dialect`), normalised once
  (`normalise_dialect`) and accepted as an alias anywhere the API takes a
  language: `ar-MSA`, `msa`, `fusha` — and the older `ar-EG`, `egyptian`,
  `masri`. Every recognised spelling resolves to `ar-MSA`; anything unknown falls
  back to the same formal register rather than failing a lesson.
* Arabic sessions are instructed to use clear, simplified Modern Standard Arabic
  for explanations while keeping technical terms in English.
* Native-audio Gemini models choose a language automatically unless constrained;
  the system instruction pins the language on every connection and after every
  failover.
* Language can be changed mid-session (`POST .../language` or the `language`
  control message). The checkpoint, questions, concept list **and the plan
  position** survive the switch; only the pipeline is re-planned.
* **A switch is spoken, not silent.** `change_language()` asks the tutor to
  acknowledge in the new language and carry on from the current step (a resume
  prompt tagged with the switch instruction when a checkpoint exists, otherwise a
  switch prompt). Without this the student kept hearing the old language until
  they happened to speak again — the bug this behaviour closes. The student's
  client sends the control message on the open socket; it never has to reconnect.
* The client sets the browser voice's `lang` to the session language, so the
  switch is audible in the demo as well as at the service level.

## The conversational layer (all ten languages)

`app/prompts/interaction.py` holds two things:

1. **`INTERACTION_SUFFIX`** — the teaching-behaviour contract appended to *every*
   system instruction. The rules that matter most, because they were asked for
   explicitly: **teach continuously rather than quizzing after each step** (a
   question has to earn its place — a tricky idea, a likely misconception, a quiet
   student); never use "is that clear?"-style check-ins, and never twice in a
   session; vary how every turn opens and never reuse a sentence inside a session;
   when the student says they don't understand, take another route (plainer words,
   an example, a smaller step) instead of repeating and without lecturing them;
   react to what they actually said and name the specific gap; never read the plan
   aloud. Real vendors follow it in prose.
2. **`INTERACTION_PHRASES`** — the same behaviour as short, speakable lines for the
   ten languages: `check`, `praise`, `rephrase`, `simpler`, `encourage`, `next`,
   `example`, `invite`, `close`, `switch`, `answer_ack`, plus templates
   (`topic_line`, `step_one`, `step_plain`, `next_step`, `on_step`, `on_current`,
   `think_of`, `smaller`, `nothing_more`) that carry the step's own wording.
3. **`PHRASE_VARIANTS`** — second and third ways to say the lines a tutor repeats
   most (`check`, `praise`, `rephrase`, `encourage`, `close`) plus `going_on` and
   `invite_stop`. The dialogue rotates them, never immediately repeating one, which
   is what stops the tutor sounding like a prompt template. `phrase_variants(lang,
   key)` returns all of them (the canonical line first) and is what the tests assert
   against.

The offline mock (`app/providers/mock/dialogue.py`) uses all three: a multilingual
keyword classifier decides whether the student agreed, objected or asked
something (a question mark beats everything; negation is checked before
agreement, so "I don't understand" is not read as "understood"), and the reply
follows the plan. It only asks a check question on roughly every second step —
otherwise it teaches on and rolls into the next step in the same turn (`going_on`),
ending with an invitation to interrupt (`invite_stop`) rather than a comprehension
quiz. Once the plan is finished it stops saying goodbye and simply answers what is
asked. Its *scaffolding* is localized; the course plan's own step
titles and goals are the catalogue's English wording — a real vendor is told to
express them in the session language. In the offline demo, curated fusHa
translations cover the demo topics (`app/curriculum_localisation.py`), so an Arabic
session is spoken entirely in Arabic; other topics keep the English plan wording
(§4 limitation 13 in the report).
