# Grounded, level-adapted explanations

When a student picks a topic from the course catalogue, the tutor does not
improvise: it teaches from **the course material plus sources this service has
vetted for that topic**, explains it **the way a human would** (picture → idea →
example → why → mistake → question), and pitches the whole thing at **the level
stored in the student's LERNA profile**. This document describes that layer:
`app/learning/levels.py`, `app/learning/sources.py`,
`app/learning/explainer.py`, `app/learner/profiles.py`, and how they are wired
into a session.

Three claims, and where each one is enforced:

| Claim | Where |
|---|---|
| The content is grounded — nothing is invented | `app/learning/sources.py` (the packs), `ExplanationBrief.prompt_block()` (the block the model must obey) |
| The explanation is level-adapted | `app/learning/levels.py` (`LevelStyle`), `app/learning/explainer.py` (`build_brief`) |
| A turn is a teaching pass, not one line and a check-in | `app/learning/lesson_script.py` (`build_script`), `app/providers/mock/dialogue.py` (`_teach_turn`), `INTERACTION_SUFFIX` |
| The level is the student's, not a guess | `app/learner/profiles.py` (`resolve_profile`), `POST /voice/session` `level`, `POST /voice/session/{id}/level` |

---

## 1. The sources (grounding)

`app/learning/sources.py` holds one **topic pack** per catalogue topic — 22
topics, 22 packs. A pack is:

```python
TopicPack(
    topic_id="binary-search",
    sources=(Source(id="src-mit-opencourseware", publisher="MIT OpenCourseWare",
                    title="…", kind="open-textbook", url="https://…",
                    why="the definition and the halving argument"), …),
    items=(Item(kind="fact", en="…", ar="…"), …),
)
```

* **`Source`** records *where the content came from*: publisher, title, kind
  (`open-textbook`, `course-notes`, `official-docs`, `reference`, `interactive`),
  a public URL, and **`why`** — the sentence that says what this source was
  chosen to support. The set is chosen the way a teacher chooses reading: the
  primary textbook (OpenStax, MIT OpenCourseWare, Khan Academy), the official
  documentation where one exists (Python's `bisect`, MDN, the ECMAScript spec),
  and a reference or interactive source for the worked example.
* **`Item`** is the *allowed claim* (`fact`), the *words that make it land*
  (`analogy`, `example`, `pitfall`, `use`) or the closing question (`check`).
  Every item carries the **canonical English** text, and — for 11 of the 22 packs
  today — a fusHa Arabic translation.
* `pack_for(topic_id)` returns the pack; `ARABIC_READY` lists the topics whose
  packs are fully translated; `all_sources()` is what a UI or an audit reads.

The rule the model is given is absolute: *every factual claim must come from the
facts in the block; if something is not covered, say you would have to check the
course material rather than guessing.*

## 2. The levels (adaptation)

`app/learning/levels.py` defines three levels and what each one demands:

| Level | Spoken clause | Teaching moves | Analogy | "What it costs" reasoning | Mistakes raised | Closing question |
|---|---|---|---|---|---|---|
| `beginner` | ≤ 11 words | picture → idea → example → fact → mistake → question | yes | no | 1 | closed ("does that land?") |
| `intermediate` | ≤ 16 words | idea → example → why → fact → mistake → question | no | yes | 1 | applied ("where would you use it?") |
| `advanced` | ≤ 24 words | idea → why → fact → example → mistake → use → question | no | yes | 2 | open ("how would you trade off …?") |

`normalise_level()` accepts what a real profile contains — `beginner`,
`intermediate`, `advanced`, `a1`/`b1`/`c2`, `first year`, `مبتدئ` — and anything
unrecognised becomes the service default rather than a failure.
`style_for(level)` returns the `LevelStyle`, whose `instruction` is the one
sentence added to the session instruction ("The student is advanced: lead with
the mechanism and the cost…").

## 3. The brief (what the tutor is told)

`build_brief(topic_id=…, language=…, level=…, plan=…)` turns a pack plus a level
into an `ExplanationBrief`:

* **`moves`** — the ordered, level-shaped explanation. Each `Move` has the
  `kind`, the **spoken** `text` (in the lesson language), the **canonical
  English** `english`, the `sources` it may cite by id, and the `concepts` it
  teaches. The closing question is always the last move.
* **`for_step(i)`** — how the moves are spread across the lesson's own
  sections, so a step never repeats another step's move.
* **`opening()`** — the first sentence, used by the offline tutor.
* **`prompt_block()`** — the block appended to the session instruction:
  the level, the teaching order, the vetted sources by name, the allowed facts,
  the worked example, the common mistake, the closing question, and the four
  rules ("your own natural words", "never guess", "match the level", "no lists,
  no markdown, no URLs"). A topic with no vetted content produces **no block**:
  the lesson then runs from the plan alone, and `grounding` is `"catalogue"`.
* **`as_dict()`** — the same brief as JSON, which is what the socket and the
  state endpoint publish.

**One language per lesson.** Arabic is taught in fusHa only, so an item a pack
has not translated for is *left out* rather than dropped into an Arabic
explanation as an English sentence; if that leaves nothing to teach, the topic
falls back to the plan (`grounding: "catalogue"`). English always has the full
pack. `fr`/`sw` have frame wording; the remaining languages use the English
frames with the model instructed to answer in the session language — live
models translate, the offline mock does not pretend to.

## 3b. The teaching pass — what a turn actually is

A vetted brief is a list of *moves*. Reading them out one per turn is the thing a
student complains about ("he says a sentence, then asks if I have a question"), so
`app/learning/lesson_script.py` turns the same moves into **passes**: the part of
the lesson being taught, its ideas developed in order, the worked example, the
trap, and a bridge into what comes next.

* **One pass per lesson section.** A sectioned pack (`section` on each `Item`)
  teaches its own part; an unsectioned pack is spread evenly across the plan, as
  before.
* **Several sentences, one topic.** Beginner 3–5, intermediate 4–6, advanced 4–7.
  A pass shorter than three sentences is a caption, not an explanation.
* **Openers rotate, then stop.** Each kind has up to five lead-ins
  (`FRAME_VARIANTS`); once they are used up a point is simply made, because no
  person prefaces every single point.
* **Not every pass asks.** Beginners are checked every second pass, intermediate
  every third, advanced every fourth — and the last pass always closes with the
  level's own question.
* **Nothing repeats inside a session.** Every grounded sentence already spoken is
  remembered, so a pass, a re-explanation and an answer never say the same
  sentence twice.

What the tutor then does with a student's words (`app/providers/mock/dialogue.py`,
mirrored in `INTERACTION_SUFFIX` for live models):

| The student says | The tutor does |
|---|---|
| "yes" / "mhmm" / anything short | Acknowledges in a few words and teaches the next pass. It does not stop to ask permission. |
| A question | Answers from the vetted material — preferring parts not yet taught — then carries on |
| "I don't get it" | Re-teaches the same part by another route: smaller clauses, the worked example, or a direct question about which piece is fuzzy. Never the same sentence again. |
| Nothing, after the plan ends | Offers what is next ("an example, or another topic?") instead of saying goodbye twice |

## 3c. Answering a question — from the whole pack, matched to the words asked

A question is not limited to the slice of the material a level teaches, so the
brief also carries an **`answer_pool`**: every vetted item of the pack in the
lesson language (19 items for binary search, against the 11 a beginner's lesson
actually walks through). When the student asks something:

1. The question and every pool item are reduced to **stems** — lowercased words
   with the common prefixes stripped, which is what lets *"ليه بنقسم لنصين؟"* meet
   the sentence about halving the range, and *"what if the data is not sorted?"*
   meet the one about sorted order being the whole assumption.
2. The best-matching items are spoken, **without** the lead-in the tutor already
   used, so the answer does not sound like a recording.
3. Matching **outranks the no-repetition rule**: if the point that answers the
   question was made two minutes ago, it comes back. Answering with something
   merely *unheard* would be worse than answering with something *relevant*.
4. Teaching then resumes from the next part that still has something new in it.

If nothing in the pack matches, the tutor says so rather than inventing:
*"that is not in the material I have for this topic — let me check the course
notes."* A fabricated answer is the one failure this layer refuses to commit.

## 4. Where the level comes from

`resolve_profile(student_id, …)` merges, in this order:

1. **the request** — `{"level": "advanced"}` on `POST /voice/session`;
2. **LERNA's Progress Profile** — read through the existing adapter
   (`LearnerContext.level`, populated from the profile document's `level`,
   `education_level`, `student_level` or `proficiency`);
3. **the local mirror** — `app/learner/profiles.py`
   (`LEARNER_PROFILE_PATH`, default `demo-data/learner_profiles.json`);
4. **the service default** — `intermediate`.

The mirror exists because the level has to survive a restart *today*, before the
website integration is switched on; it is one small JSON file, written atomically
(temp file + `os.replace`), and the running service in `app/main.py` is handed
the file-backed store while tests keep the memory-only one.

The level is **not** part of the learning state: changing it re-pitches the
explanation and touches nothing else. `POST /voice/session/{id}/level` answers
`{"detail": "level=beginner"}` and the concepts, checkpoint, questions and plan
are all still there.

## 5. What the client sees

| Surface | What it carries |
|---|---|
| `POST /voice/session` | `level` in, `student_level` out (summary and state) |
| `GET /voice/session/{id}/state` | `student_level`, `explanation {topic_id, topic, level, language, grounding, moves[], sources[], teaching_order, plan}` |
| `POST /voice/session/{id}/level` | re-pitch mid-lesson; `422` for an unknown level |
| WS `explanation.planned` | emitted when the lesson starts: `topic_id`, `topic`, `level`, `grounding`, `teaching_order`, `move_count`, `sources`, `sources_used` |
| WS `rag.retrieved` | questions are answered from the vetted sources first (`source_type: "curated"`), then LERNA's retrieval |
| Demo pages | `/topics` "Explain for" chip → `?level=` on `/voice`; the dev panel shows level, teaching order and sources; `/console` can re-pitch mid-lesson |

## 6. Proving it offline

The demo runs on mock vendors, so the same brief is handed to the offline tutor
(`metadata.explanation`), and it teaches from it: the opening sentence is a
grounded fact rather than plan wording, the closing question is the level's own,
and the lessons still never quiz after every step. Run the same topic at three
levels and listen:

```
python3 - <<'PY'
import asyncio, sys; sys.path.insert(0, ".")
from app.rag.adapter import RAGAdapter
print(asyncio.run(RAGAdapter().retrieve("how does it halve?", student_id="s1",
                                        topic_id="binary-search")).as_prompt_block())
PY
```

and over the API:

```
curl -s localhost:3000/topics                                  # the catalogue
curl -s -X POST localhost:3000/voice/session -H 'content-type: application/json' \
  -d '{"student_id":"demo","topic_id":"binary-search","language":"ar","level":"beginner"}'
curl -s -X POST localhost:3000/voice/session/<id>/level -H 'content-type: application/json' \
  -d '{"level":"advanced"}'
```

`tests/unit/test_explanation_engine.py` (35) and
`tests/integration/test_grounded_explanation.py` (11) pin all of the above
without any vendor key.

## 7. Adding a topic

1. Add the topic to `app/curriculum.py` (course, sections) — the plan is what
   checkpoints and resume speak in.
2. Add a pack to `app/learning/sources.py`: 2–4 `Source`s with `why`, then the
   teaching items. Give each item the **`section` it belongs to** (1-based, the
   plan's own order) and 3–5 items per section — the ideas of that part, its
   worked `example`, its `pitfall`, and (for the opening section) the `analogy`
   beginners get. Sectioned items are what make a pass a real explanation;
   untagged items are spread evenly instead. Finish with the `check`s (no
   section: the brief picks the one that fits the level).
3. Translate the pack to fusHa if the topic should be teachable in Arabic, and
   add its id to `ARABIC_READY`.
4. `python3 -m pytest tests/unit/test_explanation_engine.py` — the pack contract
   (sources have public URLs, every Arabic-ready topic carries Arabic) is tested
   for every pack, so a missing field fails the suite instead of reaching a
   student.

`demo-audio/teacher-turns-ar.wav` (3 m 35 s) is two full lessons recorded
straight off the socket — the same binary-search topic taught to a beginner and
to an advanced student, opening turn plus first follow-up each. Beginner gets the
dictionary picture and a closing question; advanced gets the sorted-data
assumption, the midpoint arithmetic and two mistakes, and is not asked anything
until the end.

## 8. Limits, stated plainly

* The 22 packs cover **this demo catalogue**. A production deployment generates
  the same structure from LERNA's course material (`docs/CURRICULUM.md` states
  the data shape) — the module boundary does not change.
* **11 of 22 packs** carry Arabic today; the other 11 fall back to the plan when
  the lesson is Arabic, and a backstop (`_scrub`) strips any English phrase from
  an Arabic or Amharic utterance so the tutor never switches languages mid-line.
* The level mirror is local until the Progress Profile is the source of truth;
  precedence already prefers LERNA's value the moment it answers.
* The offline mock speaks the brief; a live model receives it as instruction and
  is trusted to phrase it naturally — the block constrains *what*, not *how*.
