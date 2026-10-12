"""Round 19 docs: the explanation layer in README/API/WS/RAG/PROGRESS/report.

Run once from the service root:  python3 tools/patch_explanation_docs.py
"""
import io


def sub(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8").write(s)


# --------------------------------------------------------------------------- #
# README
# --------------------------------------------------------------------------- #

sub("README.md", [
    (
        """### What the tutor can teach""",
        """### How it explains — grounded, and pitched at the student's level

Picking a topic does not make the tutor improvise. Each of the 22 catalogue
topics carries a **vetted pack** in `app/learning/sources.py`: the sources this
service chose for it (MIT OpenCourseWare, Khan Academy, OpenStax, official docs
— each with a `why`), the facts it is allowed to teach, a picture for it, a
worked example, the mistake students actually make, and the closing question.
From that pack and the student's level, `app/learning/explainer.py` builds the
**explanation brief**: the order the explanation takes, the sentence length it
is allowed, how many mistakes to raise, and what kind of question to end on.

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

### What the tutor can teach""",
    ),
    (
        """nine route natively through Gemini Live. The same catalogue is available over
REST (`GET /curriculum/courses`) and is passed to the model as the lesson plan,""",
        """nine route natively through Gemini Live. Every topic also has a vetted pack
(22/22) that the explanation is built from — 8 of them translated to fusHa — and
`/topics` lets you choose the level to explain for, so the same lesson can be
heard three ways. The same catalogue is available over
REST (`GET /curriculum/courses`) and is passed to the model as the lesson plan,""",
    ),
    (
        """| [`docs/RAG_INTEGRATION.md`](docs/RAG_INTEGRATION.md) | How retrieval is reused, not rebuilt. |""",
        """| [`docs/EXPLANATIONS.md`](docs/EXPLANATIONS.md) | The grounded, level-adapted explanation layer: sources, levels, the brief, the profile. |
| [`docs/RAG_INTEGRATION.md`](docs/RAG_INTEGRATION.md) | How retrieval is reused, not rebuilt. |""",
    ),
    (
        """7. **Azure covers 7 of the 10 languages.** Its neural catalogue (like the""",
        """7. **The level mirror is local until the profile integration is switched
   on.** The level is read from LERNA's Progress Profile when it answers, and
   otherwise from `demo-data/learner_profiles.json`; precedence already prefers
   LERNA's value, and nothing else in the service needs to change when that
   integration goes live. The vetted packs cover the demo catalogue (22/22); a
   production deployment generates them from LERNA's own material
   (`docs/CURRICULUM.md`).
8. **Azure covers 7 of the 10 languages.** Its neural catalogue (like the""",
    ),
])

# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

sub("docs/API.md", [
    (
        """  "topic_id": "binary-search",
  "topic": "Binary Search",
  "course_id": "algorithms-101",
  "lesson_id": "lesson-binary-search",
  "document_ids": ["doc_12"],
  "resume_latest": false""",
        """  "topic_id": "binary-search",
  "topic": "Binary Search",
  "course_id": "algorithms-101",
  "lesson_id": "lesson-binary-search",
  "level": "beginner",
  "document_ids": ["doc_12"],
  "resume_latest": false""",
    ),
    (
        """`topic_id` comes from `GET /curriculum/courses` and is preferred: it brings the""",
        """`level` is `beginner` | `intermediate` | `advanced` (aliases such as `b1` or
`first year` are accepted). Leave it out and the level comes from the student's
LERNA profile, then the local mirror, then `intermediate`; an unknown level is a
`422`. The level changes how the explanation is pitched — never what the lesson
is, so checkpoints, concepts and resume are unaffected. See
`docs/EXPLANATIONS.md`.

`topic_id` comes from `GET /curriculum/courses` and is preferred: it brings the""",
    ),
    (
        """### `GET /curriculum/topics/{topic_id}`""",
        """### `POST /voice/session/{session_id}/level` → `200`

Re-pitch the explanation of the lesson in progress for another level. The
learning state is untouched: the same topic, the same checkpoint, the same
concepts, explained differently — and `explanation.planned` is emitted again.

```json
{ "level": "advanced" }
```

Response (`SimpleResponse`): `{"session_id": "...", "state": "listening",
"detail": "level=advanced"}`. An unrecognised level is a `422`.

### `GET /curriculum/topics/{topic_id}`""",
    ),
])

# --------------------------------------------------------------------------- #
# WebSocket protocol
# --------------------------------------------------------------------------- #

sub("docs/WEBSOCKET_PROTOCOL.md", [
    (
        """| `checkpoint.created` | `checkpoint {checkpoint_id, topic, section, concepts_covered, next_step, resume_instruction}` |""",
        """| `explanation.planned` | `topic_id`, `topic`, `level`, `grounding` (`curated`\\|`catalogue`), `teaching_order`, `move_count`, `sources[]`, `sources_used` — what the tutor is about to teach from, sent when the lesson starts and again when the level changes |
| `checkpoint.created` | `checkpoint {checkpoint_id, topic, section, concepts_covered, next_step, resume_instruction}` |""",
    ),
])

# --------------------------------------------------------------------------- #
# RAG integration
# --------------------------------------------------------------------------- #

sub("docs/RAG_INTEGRATION.md", [
    (
        """## When retrieval runs""",
        """## Two tiers: the vetted packs, then LERNA

`RAGAdapter.retrieve()` answers from **this service's vetted topic packs first**
(`app/learning/sources.py`, `source_type: "curated"`, `trust_score` 0.98) and
then merges whatever LERNA's own retrieval returns; duplicates are dropped by
normalised text. That ordering is what lets the tutor stay grounded with the
LERNA bridge off — and it is why an Arabic lesson says it would rather check the
course material than invent an answer. `retrieve()` accepts `topic_id` so the
caller does not have to rely on the free-text topic matching a pack.

## When retrieval runs""",
    ),
])

# --------------------------------------------------------------------------- #
# Progress profile
# --------------------------------------------------------------------------- #

sub("docs/PROGRESS_PROFILE.md", [
    (
        """## Orchestrator""",
        """## The student's level

`LearnerContext.level` (read from the profile document's `level`,
`education_level`, `student_level` or `proficiency`) is what the explanation is
pitched at: beginner, intermediate or advanced. It is surfaced to the providers
as `student_level` in the prompt context and decides the teaching order, the
allowed sentence length and the closing question — see `docs/EXPLANATIONS.md`.

The precedence is **request > profile > local mirror > service default**
(`app/learner/profiles.py`), so the website can pass a level explicitly, LERNA's
profile wins when it answers, and the local JSON mirror keeps the choice across
restarts until the integration is live. Changing the level writes it back to the
mirror and emits `explanation.planned`; it never rewrites learning state.

## Orchestrator""",
    ),
])

# --------------------------------------------------------------------------- #
# implementation report: the new row, and the honest limits
# --------------------------------------------------------------------------- #

sub("IMPLEMENTATION_REPORT.md", [
    (
        """| 5 | Smart checkpointing on *learning state*, not audio timestamps |""",
        """| 4k | **A topic added from the course is studied from the course material plus vetted sources, and explained from human logic, scaled to the student's level** (round 19) | **Yes — working end to end in the offline demo**, and unit/integration tested without any vendor key | `app/learning/sources.py` — 22 topic packs (one per catalogue topic), each a set of `Source`s (publisher, title, kind, public URL, and *why* it was chosen) plus the allowed `fact`/`analogy`/`example`/`pitfall`/`use`/`check` items, canonical English with fusHa for 8. `app/learning/levels.py` — three levels and what each demands (clause length 11/16/24, analogy only for beginners, reasoning from intermediate, 1–2 mistakes, closed/applied/open closing question). `app/learning/explainer.py` — `build_brief()` turns pack + level + lesson plan into ordered moves spread across the lesson's own sections, `prompt_block()` (what the live model must obey: allowed facts, no guessing, level, no URLs), and `as_dict()` for the wire. `app/learner/profiles.py` — the level, request > LERNA profile > local mirror > default. Surfaced as `level` on session create, `student_level` + `explanation` on the state endpoint, `POST /voice/session/{id}/level` mid-lesson, and the `explanation.planned` socket event. An Arabic lesson never mixes in English (untranslated items are left out, and the topic falls back to the plan). The offline tutor is handed the same brief, so the level is audible with no vendor key. Tests: `tests/unit/test_explanation_engine.py` (35) + `tests/integration/test_grounded_explanation.py` (11) |
| 5 | Smart checkpointing on *learning state*, not audio timestamps |""",
    ),
    (
        """15. **The Streamlit app is a developer harness, not a frontend.**""",
        """15. **The explanation layer is grounded in the demo catalogue, and its level
    mirror is local for now.** The 22 vetted packs cover `app/curriculum.py`; a
    production deployment generates the same structure from LERNA's course
    material, and 8 of the packs carry Arabic today (the rest fall back to the
    lesson plan in Arabic sessions rather than mixing languages). The level is
    read from LERNA's Progress Profile when it answers, and otherwise from
    `demo-data/learner_profiles.json` — precedence (request > profile > mirror >
    default) is already the production one.
16. **The Streamlit app is a developer harness, not a frontend.**""",
    ),
])
print("round-19 docs synced")
