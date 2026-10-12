"""Round 20: the tutor teaches — a turn is a teaching pass, not one line.

The complaint this suite pins down: "he just says a sentence and then asks if I
have a question". A teacher does not do that. A turn is several sentences that
develop one part of the lesson, the student gets the floor afterwards, and a
question from them is answered and then the lesson carries on.

Everything here runs offline, on the mock tutor, with no vendor key.
"""

from __future__ import annotations

import re

import pytest

from app.learning.explainer import build_brief
from app.learning.lesson_script import build_script
from app.providers.mock.dialogue import TutorDialogue

TOPIC = "binary-search"
PLAN = [
    {"title": "The idea of halving", "goal": "compare with the middle, discard the half"},
    {"title": "Trace it on a small array", "goal": "walk 16 elements down to 8, 4, 2, 1"},
    {"title": "Why the cost is logarithmic", "goal": "the range halves each step"},
    {"title": "Common mistakes", "goal": "unsorted input and the overflow-prone midpoint"},
]


def _tutor(level: str = "beginner", language: str = "en", topic: str = TOPIC) -> TutorDialogue:
    brief = build_brief(topic_id=topic, language=language, level=level, plan=PLAN)
    return TutorDialogue.from_metadata(
        {
            "topic_id": topic,
            "topic_title": "Binary Search",
            "sections": PLAN,
            "explanation": brief.as_dict(),
            "student_level": level,
        },
        language,
    )


#: Connective frames the explainer puts in front of a point. These are the tutor's
#: own connective tissue rather than course content, so a lesson may reuse one.
_LEAD_INS = (
    "Here is the idea.", "The whole thing rests on one idea.", "Let me give you the core of it.",
    "Start from this:", "The key is this:", "One more thing you need.", "Another piece of this.",
    "And there is this to add.", "There is more to it:", "Keep this in view:",
    "Let me put a picture in your head first.", "Picture it like this.", "Start somewhere familiar.",
    "Let us try it on something small.", "Watch it on a tiny example.", "Let us walk one case together.",
    "And here is why that works.", "Why does that hold?", "The reason is this.",
    "Watch out for this one.", "This is where people slip.", "Here is a trap to avoid.",
    "That is why we reach for it when", "You meet it whenever", "It earns its place when",
    "Good question.", "Exactly — well done.", "Take your time.", "Right.", "Mhm.",
    "I see.", "Good.", "No problem, let me put it another way.",
    "Let me come at it from another angle.", "Let me say the same thing in smaller words.",
)


def _is_lead_in(sentence: str) -> bool:
    return sentence.strip() in _LEAD_INS or sentence.strip() in _FRAMES


def _build_frames() -> set[str]:
    """The tutor's connective tissue (praise, invites, checks, closes) — these are
    frames, not course content, so the no-repeat guarantee does not apply to them."""
    from app.prompts.interaction import phrase_variants
    out: set[str] = set()
    for key in ("invite", "close", "praise", "encourage", "check", "answer_ack", "invite_stop"):
        for variant in phrase_variants("en", key):
            out.add(variant.strip())
            out.add((variant.rstrip("?.!") + ".").strip())
            out.add((variant.rstrip("?.!") + "?").strip())
    return out


_FRAMES = _build_frames()


def _sentences(text: str) -> list[str]:
    """Spoken sentences: split after ".", "?" or "؟", wherever a pause is written."""
    parts = re.split(r"(?<=[.?!\u061f])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


# --------------------------------------------------------------------------- #
# a turn is a teaching pass
# --------------------------------------------------------------------------- #


def test_the_first_turn_teaches_a_whole_part_of_the_lesson():
    dialogue = _tutor("beginner")
    opening = dialogue.opening()
    first = dialogue.script.passes[0]
    assert first.sentence_count() >= 4, first.as_dict()
    assert len(opening) > 260, opening          # not one line and a check-in
    # It says the part it is teaching, in the pack's own words.
    assert first.sentences[0].split(".")[0][:24] in opening
    # Five to nine sentences a teacher would actually say before pausing.
    assert 4 <= len(_sentences(opening)) <= 14


def test_every_lesson_part_gets_its_own_pass_in_plan_order():
    dialogue = _tutor("intermediate")
    script = dialogue.script
    assert len(script) == len(PLAN)
    for index, step in enumerate(PLAN):
        assert step["title"] in script.passes[index].section


def test_a_teaching_pass_is_several_sentences_at_every_level():
    for level in ("beginner", "intermediate", "advanced"):
        script = _tutor(level).script
        for item in script.passes:
            assert item.sentence_count() >= 3, (level, item.as_dict())
    # ... and the beginner's prose is shorter to listen to, sentence by sentence.
    beginner = max(len(s.split()) for s in _tutor("beginner").script.passes[0].sentences)
    advanced = max(len(s.split()) for s in _tutor("advanced").script.passes[0].sentences)
    assert beginner <= advanced


def test_the_tutor_does_not_ask_a_question_after_every_pass():
    for level, allowed in (("beginner", 3), ("intermediate", 3), ("advanced", 2)):
        script = _tutor(level).script
        asked = sum(1 for item in script.passes if item.question)
        assert asked <= allowed, (level, asked)
        assert script.passes[-1].question, "the lesson still closes with one question"


# --------------------------------------------------------------------------- #
# interactivity: react, answer, keep teaching
# --------------------------------------------------------------------------- #


def test_saying_yes_moves_to_the_next_pass_and_keeps_teaching():
    dialogue = _tutor("beginner")
    dialogue.opening()
    turn = dialogue.respond("yes")
    assert len(turn) > 200, turn
    assert dialogue.pass_index == 1
    # It teaches the next part, not a one-line summary of it.
    assert dialogue.script.passes[1].sentences[0][:24] in turn


def test_a_question_is_answered_then_confirmed_then_resumed():
    """Round 22: answer → ask "all clear?" → resume from where it stopped."""
    dialogue = _tutor("beginner")
    dialogue.opening()
    asked = dialogue.respond("why does that work?")
    # The answer is grounded: the vetted pack's own wording, from the whole pack.
    pool = [m["text"] for m in dialogue.explanation["answer_pool"]]
    assert pool, "the brief must carry the whole vetted pack for answering"
    assert any(part in asked for part in pool), asked
    # It does not jump ahead on its own: it asks, then waits.
    assert dialogue.pass_index == 0, "the lesson holds where it was while it asks"
    assert dialogue._awaiting_continue is True
    assert "?" in asked, "the tutor asks whether it is all clear"
    # Once the student confirms, it resumes from the part that follows.
    resumed = dialogue.respond("yes")
    assert dialogue._awaiting_continue is False
    assert dialogue.pass_index == 1, "the lesson carried on from where it stopped"
    assert dialogue.script.passes[1].sentences[0][:24] in resumed


def test_a_second_question_after_the_answer_keeps_holding_the_lesson():
    """If they ask again instead of confirming, it answers and asks again."""
    dialogue = _tutor("beginner")
    dialogue.opening()
    dialogue.respond("why does that work?")
    again = dialogue.respond("and what if it is not sorted?")
    assert dialogue.pass_index == 0, "still parked at the same part"
    assert dialogue._awaiting_continue is True
    assert "?" in again
    pool = [m["text"] for m in dialogue.explanation["answer_pool"]]
    assert any(part in again for part in pool), again


def test_confusion_re_teaches_the_same_part_by_another_route():
    dialogue = _tutor("beginner")
    dialogue.opening()
    first = dialogue.respond("I don't understand")
    second = dialogue.respond("still lost")
    assert first != second, "never the same re-explanation twice"
    assert "?" in second or len(second) > 60
    # It stays on the same part instead of marching on.
    assert dialogue.pass_index == 0


def test_the_teacher_still_answers_once_the_plan_runs_out():
    """Finishing the sections is not the end of the conversation."""
    dialogue = _tutor("beginner")
    dialogue.opening()
    for _ in range(6):
        dialogue.respond("yes")
    assert dialogue.done, "the plan really is finished"
    turn = dialogue.respond("what is the difference from a normal search?")
    assert len(turn) > 120, turn
    pool = [m["text"] for m in dialogue.explanation["answer_pool"]]
    assert any(part in turn for part in pool), turn


def test_confusion_after_the_end_re_explains_instead_of_closing():
    dialogue = _tutor("beginner")
    dialogue.opening()
    for _ in range(6):
        dialogue.respond("yes")
    turn = dialogue.respond("still don't get it")
    assert "?" in turn or len(turn) > 60, turn


def test_no_sentence_is_spoken_twice_in_a_session():
    """A point already made is not made again — unless the student asks for it.

    Answering a direct question may legitimately bring a point back (better than
    answering with something irrelevant); teaching it a second time uninvited is
    what this pins down.
    """
    dialogue = _tutor("advanced")
    turns = [dialogue.opening()]
    for text in ("yes", "mhmm", "keep going", "yes", "ok"):
        turns.append(dialogue.respond(text))
    seen: set[str] = set()
    for turn in turns:
        for sentence in _sentences(turn):
            if _is_lead_in(sentence):
                continue          # a frame, not content — frames are allowed to recur
            assert sentence not in seen, f"repeated: {sentence}"
            seen.add(sentence)


def test_a_question_is_answered_with_the_point_it_is_about():
    """Relevance, not rotation: the pack sentence that answers *this* question."""
    dialogue = _tutor("beginner")
    asked = dialogue.respond("what if the data is not sorted?")
    pool = {m["text"] for m in dialogue.explanation["answer_pool"]}
    spoken = [s for s in _sentences(asked) if s in pool]
    assert spoken, asked
    assert any("sorted" in s.lower() or "unordered" in s.lower() for s in spoken), spoken

    other = _tutor("beginner").respond("how many comparisons for a million items?")
    other_spoken = [s for s in _sentences(other) if s in pool]
    assert any("million" in s or "twenty" in s for s in other_spoken), other_spoken


# --------------------------------------------------------------------------- #
# grounded, and in one language
# --------------------------------------------------------------------------- #


def test_the_offline_teaching_pass_stays_on_the_vetted_material():
    dialogue = _tutor("advanced")
    teaching = dialogue.script.all_text()
    # Every pass carries at least one grounded move, and the sources are named.
    for item in dialogue.script.passes:
        assert item.kinds, item.section
        assert item.sources, item.section
    assert "sorted" in teaching.lower()          # the pack's own fact
    assert len(teaching) > 1200, "a lesson's worth of explanation, not a summary"


def test_an_arabic_lesson_is_taught_in_arabic_only():
    dialogue = _tutor("beginner", language="ar")
    for sentence in _sentences(dialogue.script.all_text()):
        letters = [ch for ch in sentence if ch.isalpha()]
        if not letters:
            continue
        arabic = sum(1 for ch in letters if "\u0600" <= ch <= "\u06ff")
        assert arabic / len(letters) > 0.6, sentence


def test_a_question_in_any_spelling_is_answered():
    from app.providers.mock.dialogue import classify, Intent

    asked = [
        "why does it work?",                       # english
        "ليه؟",                                    # arabic, fusHa and Egyptian
        "ما الفرق بين البحث الثنائي والعادي؟",      # arabic, formal
        "እንዴት፧",                                   # amharic question mark
        "ทำไม?",                                    # thai
        "え、どういうこと？",                            # full-width
    ]
    for text in asked:
        assert classify(text) is Intent.QUESTION, text


def test_the_goodbye_is_said_once_and_the_floor_stays_open():
    dialogue = _tutor("beginner")
    dialogue.opening()
    for _ in range(6):
        dialogue.respond("yes")
    first = dialogue.respond("ok")
    second = dialogue.respond("ok")
    assert first != second, "the same goodbye twice is a script, not a teacher"
    asked = dialogue.respond("what if the array is empty?")
    pool = [m["text"] for m in dialogue.explanation["answer_pool"]]
    assert any(part in asked for part in pool), asked


def test_the_script_is_built_from_the_brief_it_was_given():
    brief = build_brief(topic_id=TOPIC, language="en", level="intermediate", plan=PLAN)
    script = build_script(
        topic=brief.topic,
        language="en",
        level="intermediate",
        moves=brief.moves,
        sections=PLAN,
    )
    kinds = [k for item in script.passes for k in item.kinds]
    assert sorted(kinds) == sorted(m.kind for m in brief.moves if m.kind != "check")
    assert script.at(99) is script.passes[-1]      # clamped, never out of range
    assert script.at(-5) is script.passes[0]


def test_a_topic_without_a_pack_keeps_the_old_plan_wording():
    dialogue = TutorDialogue.from_metadata(
        {"topic_title": "Quantum Knitting", "sections": PLAN}, "en"
    )
    assert dialogue.script is None
    assert dialogue.opening()          # still teaches from the plan


# --------------------------------------------------------------------------- #
# round 22: an Arabic session stays Arabic, and teaches the whole topic
# --------------------------------------------------------------------------- #

_EN_PHRASE = re.compile(r"[A-Za-z][A-Za-z-']*(?: +[A-Za-z-']+){2,}")
_BIOLOGY = ("cell-structure", "dna-rna", "photosynthesis")


def test_biology_is_taught_in_easy_arabic_with_no_english_mixed_in():
    """The screenshot bug: an Arabic lesson must not switch to English mid-sentence.

    These three biology topics had no Arabic material, so the tutor fell back to
    English scaffolding. They now teach fully in Arabic, and the no-English backstop
    catches any phrase that slips through.
    """
    for topic in _BIOLOGY:
        dialogue = _tutor("beginner", language="ar", topic=topic)
        assert dialogue.teaching, f"{topic}: the brief must teach, not read a plan"
        turns = [dialogue.opening()]
        for reply in ("نعم", "مش فاهم", "سؤال: ليه؟", "نعم", "نعم"):
            turns.append(dialogue.respond(reply))
        for turn in turns:
            assert not _EN_PHRASE.search(turn), f"{topic}: English leaked -> {turn}"
            letters = [c for c in turn if c.isalpha()]
            if letters:
                arabic = sum(1 for c in letters if "\u0600" <= c <= "\u06ff")
                assert arabic / len(letters) > 0.6, f"{topic}: {turn}"


def test_an_arabic_session_teaches_the_whole_topic_not_one_line():
    """Round 22: 'explain the whole topic' — several passes, all of them taught."""
    dialogue = _tutor("beginner", language="ar", topic="cell-structure")
    dialogue.opening()
    taught = {dialogue.pass_index}
    for _ in range(len(dialogue.script) + 2):
        dialogue.respond("نعم")
        taught.add(dialogue.pass_index)
    assert len(taught) >= len(dialogue.script), "every part of the topic was reached"
    assert dialogue.done, "the whole topic was taught to the end"


def test_a_quiet_student_gets_exactly_one_question_at_the_end():
    """Round 23: teach straight through; only at the very end ask 'any questions?'."""
    from app.prompts.interaction import phrase
    invite = phrase("en", "invite")
    dialogue = _tutor("beginner")
    before = [dialogue.opening()]
    finish = None
    for _ in range(8):
        turn = dialogue.respond("yes")
        if dialogue.done:
            finish = turn
            break
        before.append(turn)
    assert finish is not None, "the lesson must actually finish"
    assert invite in finish, "the quiet student is asked once, at the end"
    # Nothing during the lesson was a check-in question.
    for turn in before:
        assert invite not in turn, turn


def test_a_student_who_asked_is_not_asked_again_at_the_end():
    from app.prompts.interaction import phrase
    invite = phrase("en", "invite")
    dialogue = _tutor("beginner")
    dialogue.opening()
    dialogue.respond("why does that work?")   # they asked
    dialogue.respond("yes")                    # confirm -> resume
    finish = None
    for _ in range(6):
        turn = dialogue.respond("yes")
        if dialogue.done:
            finish = turn
            break
    assert finish is not None
    assert invite not in finish, "a student who already asked just gets the close"
