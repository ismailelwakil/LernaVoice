"""Docs + report for the humanised conversation and the live-voice knobs."""

# ============================================================ .env.example
P = ".env.example"
s = open(P).read()
s = s.replace(
    """GEMINI_VOICE_NAME=Kore
""",
    """GEMINI_VOICE_NAME=Kore
# Native-audio live models can adapt their tone to how the student sounds.
GEMINI_AFFECTIVE_DIALOG=true
# Let the model speak up when it has something useful to add (off: a tutor answers,
# it does not fill every silence).
GEMINI_PROACTIVE_AUDIO=false
""",
)
open(P, "w").write(s)

# ============================================================ README
P = "README.md"
s = open(P).read()
s = s.replace("with 205 passing", "with 219 passing")
s = s.replace("# 205 tests", "# 219 tests")

s = s.replace(
    """| Conversational tutoring | Teach one idea → stop and check → react to the answer. "I don't understand" gets a *different* explanation, not the same paragraph again. Live language switch acknowledged in the new language. |""",
    """| Conversational tutoring | Teaches continuously and reacts to the answer — *not* a quiz after every step. "I don't understand" gets a different route, never the same paragraph again. Wording rotates instead of repeating, and a live language switch is acknowledged in the new language. |""",
)

old = """| You say | The tutor does |
|---|---|
| "yes" / "نعم" / "yebo" | praises specifically and teaches the next plan step |
| "I don't understand" / "مش فاهم" | rephrases — and a second complaint gets a different route, never the same sentence |
| "what is the midpoint?" | answers, stays on the current step, invites a follow-up |
| *(switches language in the picker)* | acknowledges **in the new language** and continues the same step |"""

new = """| You say | The tutor does |
|---|---|
| "yes" / "نعم" / "yebo" | teaches the next step — and often keeps going into the one after it instead of asking you to confirm again |
| "I don't understand" / "مش فاهم" | rephrases by another route (plainer words → smaller step → example), never the same sentence twice, and does not lecture you for asking |
| "what is the midpoint?" | answers, stays on the current step, invites a follow-up |
| *(nothing — you just let it talk)* | keeps teaching; it only asks something when it earns its place |
| *(switches language in the picker)* | acknowledges **in the new language** and continues the same step |

Rules the tutor is held to (asserted in `tests/unit/test_interaction_layer.py`): never
reuse a sentence inside a session, never use an "is that clear?"-style check-in, vary how
every turn opens, and use your name occasionally rather than constantly."""
assert old in s
s = s.replace(old, new)

# live-voice pointer in the quick start
old2 = """Demo harness (testing only, **not** the production frontend):"""
new2 = """### Turning on the real voice

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

Demo harness (testing only, **not** the production frontend):"""
assert old2 in s
s = s.replace(old2, new2, 1)
open(P, "w").write(s)

# ============================================================ docs/LANGUAGES.md
P = "docs/LANGUAGES.md"
s = open(P).read()
old3 = """`app/prompts/interaction.py` holds two things:

1. **`INTERACTION_SUFFIX`** — the teaching-behaviour contract appended to *every*
   system instruction: teach one idea then stop and check; react to what the
   student actually said (name the specific gap when they are wrong); never
   repeat the sentence you just said when the student says they don't understand;
   offer a choice when they are quiet; ask one question at a time; never read the
   plan aloud. Real vendors follow it in prose."""
new3 = """`app/prompts/interaction.py` holds two things:

1. **`INTERACTION_SUFFIX`** — the teaching-behaviour contract appended to *every*
   system instruction. The rules that matter most, because they were asked for
   explicitly: **teach continuously rather than quizzing after each step** (a
   question has to earn its place — a tricky idea, a likely misconception, a quiet
   student); never use "is that clear?"-style check-ins, and never twice in a
   session; vary how every turn opens and never reuse a sentence inside a session;
   when the student says they don't understand, take another route (plainer words,
   an example, a smaller step) instead of repeating and without lecturing them;
   react to what they actually said and name the specific gap; never read the plan
   aloud. Real vendors follow it in prose."""
assert old3 in s
s = s.replace(old3, new3)

old4 = """2. **`INTERACTION_PHRASES`** — the same behaviour as short, speakable lines for the
   ten languages: `check`, `praise`, `rephrase`, `simpler`, `encourage`, `next`,
   `example`, `invite`, `close`, `switch`, `answer_ack`, plus templates
   (`topic_line`, `step_one`, `next_step`, `on_step`, `on_current`, `think_of`,
   `smaller`, `nothing_more`) that carry the step's own wording."""
new4 = """2. **`INTERACTION_PHRASES`** — the same behaviour as short, speakable lines for the
   ten languages: `check`, `praise`, `rephrase`, `simpler`, `encourage`, `next`,
   `example`, `invite`, `close`, `switch`, `answer_ack`, plus templates
   (`topic_line`, `step_one`, `step_plain`, `next_step`, `on_step`, `on_current`,
   `think_of`, `smaller`, `nothing_more`) that carry the step's own wording.
3. **`PHRASE_VARIANTS`** — second and third ways to say the lines a tutor repeats
   most (`check`, `praise`, `rephrase`, `encourage`, `close`) plus `going_on` and
   `invite_stop`. The dialogue rotates them, never immediately repeating one, which
   is what stops the tutor sounding like a prompt template. `phrase_variants(lang,
   key)` returns all of them (the canonical line first) and is what the tests assert
   against."""
assert old4 in s
s = s.replace(old4, new4)

s = s.replace(
    """The offline mock (`app/providers/mock/dialogue.py`) uses both: a multilingual
keyword classifier decides whether the student agreed, objected or asked
something (a question mark beats everything; negation is checked before
agreement, so "I don't understand" is not read as "understood"), and the reply
follows the plan.""",
    """The offline mock (`app/providers/mock/dialogue.py`) uses all three: a multilingual
keyword classifier decides whether the student agreed, objected or asked
something (a question mark beats everything; negation is checked before
agreement, so "I don't understand" is not read as "understood"), and the reply
follows the plan. It only asks a check question on roughly every second step —
otherwise it teaches on and rolls into the next step in the same turn (`going_on`),
ending with an invitation to interrupt (`invite_stop`) rather than a comprehension
quiz. Once the plan is finished it stops saying goodbye and simply answers what is
asked.""",
)
open(P, "w").write(s)

# ============================================================ docs/PROVIDERS.md
P = "docs/PROVIDERS.md"
s = open(P).read()
anchor = "\n## "
idx = s.find(anchor, s.find("# "))
section = """
## Gemini Live configuration

The setup message the provider sends carries, besides the model, system instruction,
tools and transcriptions:

| Field | Setting | Why |
|---|---|---|
| `speech_config` | `GEMINI_VOICE_NAME` (default `Kore`) | the voice the student hears |
| `enable_affective_dialog` | `GEMINI_AFFECTIVE_DIALOG` (default `true`) | native-audio models adapt tone to how the student sounds instead of narrating flatly |
| `proactivity.proactive_audio` | `GEMINI_PROACTIVE_AUDIO` (default `false`) | lets the model speak up unprompted; off by default because a tutor should answer, not fill every silence |

The optional fields are attempted first and dropped automatically if the model or auth
path rejects them (`_looks_like_setup_rejection`), so an older live model still connects;
a genuine network failure is *not* retried and fails over as usual. Both paths are
supported and selected by env:

```
GOOGLE_GENAI_USE_VERTEXAI=true   + GOOGLE_CLOUD_PROJECT + ADC/service account → gemini-3.8-live
GOOGLE_GENAI_USE_VERTEXAI=false  + GEMINI_API_KEY (AIza…)                     → gemini-2.5-flash-native-audio-preview-12-2025
```
"""
if "Gemini Live configuration" not in s:
    s = s[:idx] + section + s[idx:]
open(P, "w").write(s)

# ============================================================ IMPLEMENTATION_REPORT
P = "IMPLEMENTATION_REPORT.md"
s = open(P).read()
s = s.replace("**205/205 automated tests", "**219/219 automated tests")
s = s.replace("| 205 tests, offline |", "| 219 tests, offline |")
s = s.replace("# 205 passed", "# 219 passed")

s = s.replace(
    "| 4b | Conversational teaching behaviour — one idea, then check; reacts to the actual answer; rephrases instead of repeating | **Yes** | `app/prompts/interaction.py` (`INTERACTION_SUFFIX`, appended to every system instruction) + `app/providers/mock/dialogue.py`; `tests/unit/test_interaction_layer.py` |",
    "| 4b | Humanised tutoring — teaches continuously rather than quizzing after every step; reacts to the actual answer; rephrases another way; wording rotates so nothing is repeated | **Yes** | `INTERACTION_SUFFIX` (rules asserted in `tests/unit/test_interaction_layer.py`) + `PHRASE_VARIANTS` rotation in `app/providers/mock/dialogue.py`; a whole-plan walk is checked to contain at most one check-in and at least one teaching turn with no question at all |",
)
s = s.replace(
    "| 4c | Mid-lesson language switch is **heard** in the new language, at the same plan step | **Yes** |",
    "| 4c | Live voice configured for the native-audio model: affective dialog on, proactive audio optional, voice selectable, optional fields dropped if the model rejects them | **Yes (unit-tested; not exercised against a live vendor)** | `app/providers/gemini/live.py`, `GEMINI_AFFECTIVE_DIALOG` / `GEMINI_PROACTIVE_AUDIO` / `GEMINI_VOICE_NAME`; `tests/unit/test_live_voice_config.py` records the setup payload a stub client receives |\n| 4d | Mid-lesson language switch is **heard** in the new language, at the same plan step | **Yes** |",
)

old_row = "| 29 | pytest suites incl. mocks, no paid credentials | **Yes** | 205 tests, offline |"
if old_row in s:
    s = s.replace(old_row, "| 29 | pytest suites incl. mocks, no paid credentials | **Yes** | 219 tests, offline |")

anchor2 = "| Topic catalogue over HTTP |"
row = """| Humanised dialogue over WS (live, mock vendors) | Opening teaches step one and *hands the turn over* ("Jump in whenever you want") instead of quizzing; one check-in in a four-step walk; merged turns teach two steps without a question; varied praise each turn; the plan closes once and questions are still answered afterwards |
| `/health` with no keys | `{"mock_providers": true, "gemini_auth": "none", "live_model": "gemini-2.5-flash-native-audio-preview-12-2025", "live_models": {"vertex": "gemini-3.8-live", ...}}` — the shape of the pipeline, never a credential |
| Topic catalogue over HTTP |"""
if "Humanised dialogue over WS" not in s:
    s = s.replace(anchor2, row, 1)
open(P, "w").write(s)

# ============================================================ docs/TESTING.md
P = "docs/TESTING.md"
s = open(P).read()
s = s.replace("| **Total** | | **205 passing** |", "| **Total** | | **219 passing** |")
s = s.replace(
    "dialogue policy) | 83 |",
    "dialogue policy, plus the live-voice setup payload) | 97 |",
)
open(P, "w").write(s)
print("docs updated")
