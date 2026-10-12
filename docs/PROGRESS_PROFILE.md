# Progress Profile integration

Voice is a **modality**, not a separate learner model. Everything the tutor
learns about the student is written back into LERNA's existing Progress Profile
(`StudentProfile`), and everything it knows about the student is read from it.

## Read path — personalising the lesson

On `start`, `ProgressAdapter.get_context(student_id)` loads the profile through
the bridge and projects it into prompt context:

| Prompt field | Source on `StudentProfile` |
|---|---|
| `mastered_concepts` | `concept_mastery` (above threshold) |
| `weak_concepts` | `weak_concepts` |
| `prerequisite_gaps` | `prerequisite_gaps` |
| `known_misconceptions` | `misconceptions` |
| `recent_topics` | `recent_topics` |
| `learning_preference`, `course`, `student_name` | profile metadata |

The tutor is instructed to target weak concepts, pre-empt known misconceptions
and not re-teach mastered material.

## Write path — learning signals

| Signal kind | Raised when |
|---|---|
| `concept_discussed` | a concept is covered in the lesson |
| `concept_understood` | the student demonstrates understanding |
| `question_asked` | the student interrupts with a question |
| `misconception_detected` | the model calls `record_learning_signal` with a misconception |
| `concept_completed` | a section finishes |
| `needs_reinforcement` | the student struggles or asks repeatedly |

### Concepts are stored in English, whatever language the lesson was taught in

The profile is matched against the curriculum, so a concept stored as
`فكرة التنصيف` would be unusable downstream. Every concept that
reaches state, checkpoints or the profile therefore goes through
`app/learner/canonical_concepts.py` first:

* a **localised** title, goal or fragment of one (from the curated translations)
  resolves to that section's English catalogue phrase;
* **English** wording is stored exactly as the tutor said it, with
  `catalogue_ref` naming the curriculum phrase it matches, if any;
* anything unresolvable is stored as spoken with `canonical: false` and its
  `language`, so nothing is silently invented — the profile can be reconciled
  later rather than corrupted now.

Signals are emitted to the client as `learning.signal`, stored on the session,
and forwarded to the profile via the bridge (`module.tutor.store.load/save` in
in-process mode). Each carries `student_id`, `session_id`, `concept`, `kind`,
`confidence`, `language`, `timestamp` and `modality: "voice"`, plus — when the
lesson was not in English — `spoken_as` (the wording the student heard),
`canonical` and `catalogue_ref`.

The offline tutor follows the same rule: when it finishes a plan step it reports
that step's **English** concept through `update_lesson_position`, so an Arabic
lesson still fills the profile with `The idea of halving`, `Trace it on a small
array`, and so on.

## The student's level

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

## Orchestrator

`app/learner/orchestrator_adapter.py` registers the voice modality for the
session and can ask LERNA's Learning Orchestrator for the next action
(`continue_lesson`, `review`, `assess`, …), which seeds `next_step` on
checkpoints and the end-of-session `next_action`.

## Session summary

On `end`, the service writes a summary containing topic, concepts covered,
questions asked, unresolved questions, detected misconceptions and the
recommended next action. That is what a returning session recaps from.

## Failure behaviour

If the Progress Profile is unreachable, signals are queued on the session
document and the lesson continues. Learning data is never silently lost, and a
profile outage never interrupts the student.
