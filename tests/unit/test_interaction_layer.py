"""The conversational layer: behaviour contract, phrases, intent, dialogue (§43-§44).

These tests are offline by design — the mock dialogue is what makes the demo
audible without vendor keys, and the phrase tables are the same contract a real
model is given in prose.
"""

from __future__ import annotations

import re

import pytest

from app.prompts.interaction import (
    INTERACTION_PHRASES,
    INTERACTION_SUFFIX,
    PHRASE_VARIANTS,
    LANGUAGE_SWITCH_MARKER,
    build_language_switch_prompt,
    is_language_switch_prompt,
    phrase,
    phrase_variants,
    react,
    move_on,
    speakable,
    step_lead,
)
from app.prompts.languages import LANGUAGE_INSTRUCTIONS
from app.prompts.resume import build_resume_prompt
from app.prompts.system import build_system_instruction
from app.providers.mock.dialogue import Intent, TutorDialogue, classify

LANGUAGES = ("en", "ar", "fr", "sw", "am", "ha", "so", "yo", "ig", "zu")
PHRASE_KEYS = (
    "check",
    "praise",
    "rephrase",
    "simpler",
    "encourage",
    "next",
    "example",
    "invite",
    "close",
    "switch",
    "answer_ack",
)

SECTIONS = [
    {"title": "What makes binary search possible", "goal": "sorted order is the precondition"},
    {"title": "Choosing the midpoint", "goal": "mid = (low + high) // 2"},
    {"title": "Halving the search space", "goal": "discard the impossible half"},
    {"title": "Stopping condition", "goal": "know when the target is absent"},
]


# --------------------------------------------------------------------------- #
# the behaviour contract
# --------------------------------------------------------------------------- #


def test_system_instruction_carries_the_interaction_contract():
    instruction = build_system_instruction(language="ar")
    assert INTERACTION_SUFFIX in instruction
    # The contract is about *teaching behaviour*, not decoration.
    for promise in (
        "Never reuse a sentence",
        "do not lecture them for it",
        "Never read the plan aloud",
    ):
        assert promise in instruction
    assert "LANGUAGE" in instruction


def test_the_contract_forbids_interrogating_after_every_step():
    """The behaviour asked for explicitly: teach on, don't check in every part.

    A tutor that ends every step with "does that make sense so far?" is the thing
    this contract exists to prevent, so the rule is asserted, not just written.
    """
    text = " ".join(INTERACTION_SUFFIX.lower().split())  # rules span lines in the source
    assert "do not have to ask a question at the end of every step" in text
    assert "never use \"is that clear?\" style check-ins" in text
    assert "only when it earns its place" in text
    assert "vary how you open every single turn" in text
    assert "never reuse a sentence" in text


def test_interaction_contract_travels_with_every_language_and_context():
    for language in LANGUAGES:
        instruction = build_system_instruction(
            language=language,
            lesson_context={"topic": "Binary Search", "lesson_plan": ["1. One", "2. Two"]},
            checkpoint={"section": "Choosing the midpoint"},
        )
        assert INTERACTION_SUFFIX in instruction, language
        assert LANGUAGE_INSTRUCTIONS[language].strip()[:24] in instruction, language


def test_every_language_has_every_interaction_phrase():
    for language in LANGUAGES:
        table = INTERACTION_PHRASES[language]
        for key in PHRASE_KEYS:
            assert table.get(key, "").strip(), f"{language}/{key}"


def test_phrases_are_actually_translated_and_speakable():
    for language in LANGUAGES:
        if language == "en":
            continue
        table = INTERACTION_PHRASES[language]
        # A copy-pasted English string would mean the tutor switches language mid-sentence.
        assert table["check"] != INTERACTION_PHRASES["en"]["check"], language
        for key in PHRASE_KEYS:
            line = table[key]
            assert not re.search(r"[<>_*#]", line), f"{language}/{key}: {line}"
            assert len(line) < 200, f"{language}/{key}"


def test_unknown_language_falls_back_to_english():
    assert phrase("xx", "check") == INTERACTION_PHRASES["en"]["check"]
    assert phrase(None, "check") == INTERACTION_PHRASES["en"]["check"]


# --------------------------------------------------------------------------- #
# switching language mid-lesson
# --------------------------------------------------------------------------- #


def test_language_switch_prompt_is_detectable_and_speaks_the_new_language():
    prompt = build_language_switch_prompt("ar", section="Choosing the midpoint", topic="Binary Search")
    assert is_language_switch_prompt(prompt)
    assert LANGUAGE_SWITCH_MARKER in prompt
    assert "Arabic (ar)" in prompt
    assert "Choosing the midpoint" in prompt and "Binary Search" in prompt
    # It must forbid a restart or a translation of what was already said.
    assert "not restart" in prompt and "not translate" in prompt
    assert not is_language_switch_prompt("The student asked (in English): \"why?\"")


def test_resume_prompt_can_announce_a_language_switch():
    checkpoint = {"topic": "Binary Search", "section": "Choosing the midpoint", "concepts_covered": ["sorted order"]}
    plain = build_resume_prompt(language="ar", checkpoint=checkpoint)
    switched = build_resume_prompt(language="ar", checkpoint=checkpoint, language_switch=True)

    assert not is_language_switch_prompt(plain)
    assert is_language_switch_prompt(switched)
    assert switched.startswith(LANGUAGE_SWITCH_MARKER)
    # The resume content survives: it resumes, it does not restart.
    assert "sorted order" in switched and "Choosing the midpoint" in switched


# --------------------------------------------------------------------------- #
# understanding what the student said
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text",
    [
        "yes", "yep", "ok", "got it", "I understand", "sure, continue",
        "نعم", "تمام", "أفهم", "oui", "d'accord",
        "ndiyo", "nimeelewa", "sawa", "አዎ", "ገባኝ", "na gane", "waan fahmay",
        "bẹ́ẹ̀ ni", "ee", "yebo", "ngiyaqonda",
    ],
)
def test_agreement_is_read_as_agreement(text):
    assert classify(text) is Intent.AFFIRM, text


@pytest.mark.parametrize(
    "text",
    [
        "no", "I don't understand", "not really", "I'm confused", "didn't understand that",
        "لا أفهم", "مش فاهم", "لست فاهما", "non", "hapana", "sielewi",
        "አልገባኝም", "ban gane ba", "ma fahmin", "mba", "cha",
        "still lost", "not following", "this is confusing", "makes no sense",
    ],
)
def test_confusion_is_read_as_confusion(text):
    assert classify(text) is Intent.CONFUSED, text


def test_i_dont_understand_is_not_read_as_agreement():
    # Both sentences share the "understand" stem — order of checks matters.
    assert classify("I don't understand") is Intent.CONFUSED
    assert classify("didn't understand that") is Intent.CONFUSED


def test_a_question_mark_wins_over_everything():
    assert classify("yes, but why?") is Intent.QUESTION
    assert classify("I don't understand, what is a midpoint?") is Intent.QUESTION
    assert classify("هل يمكنك التوضيح؟") is Intent.QUESTION


def test_statements_have_no_intent():
    assert classify("the array must be sorted") is Intent.OTHER
    assert classify("") is Intent.OTHER


# --------------------------------------------------------------------------- #
# the dialogue policy itself
# --------------------------------------------------------------------------- #


def _dialogue(language: str = "en") -> TutorDialogue:
    return TutorDialogue.from_metadata(
        {"topic_id": "binary-search", "topic_title": "Binary Search", "sections": SECTIONS},
        language,
    )


def test_opening_greets_in_language_names_the_topic_and_teaches_one_step():
    for language in LANGUAGES:
        line = TutorDialogue.from_metadata(
            {"topic_title": "Binary Search", "sections": SECTIONS}, language
        ).opening()
        assert line.strip(), language
        assert "Binary Search" in line, language
        # The step is spoken as a sentence in the language's own frames — no "Step 1:"
        # label, no em dash recitation (that is what sounded like a machine reading).
        assert "Step one" not in line and "Step 1" not in line, language
        assert "—" not in line.split("Jump")[0], language
        assert SECTIONS[0]["title"].lower() in line.lower(), language
        assert SECTIONS[0]["goal"].split(".")[0].lower() in line.lower(), language
        assert line.startswith(TutorDialogue.from_metadata(None, language).opening()[:4]), language


def test_english_scaffolding_never_leaks_into_another_language():
    """A switch to Arabic/Zulu must not leave English sentence frames behind."""
    english_only = ("Today we are working on", "Step one:", "Next:", "Right — we're on", "nothing more than that")
    keys = (
        "check", "praise", "rephrase", "simpler", "encourage", "next", "example", "invite",
        "close", "switch", "answer_ack", "going_on", "invite_stop", "on_step", "on_current",
        "smaller", "think_of",
    )
    for language in LANGUAGES:
        if language == "en":
            continue
        dialogue = _dialogue(language)
        lines = [
            dialogue.opening(),
            dialogue.respond("yes"),
            dialogue.respond("I don't understand"),
            dialogue.respond("what is the midpoint?"),
            dialogue.language_switch(),
        ]
        for line in lines:
            for phrase_ in english_only:
                assert phrase_ not in line, f"{language}: {line}"
            # every turn carries at least one line of the lesson language's own wording
            assert any(v and v in line for key in keys for v in phrase_variants(language, key)), line

    english = _dialogue().opening()
    assert "Binary Search" in english
    # It hands the floor over rather than checking comprehension on turn one.
    assert any(v in english for v in phrase_variants("en", "invite_stop")), english
    assert not any(v in english for v in phrase_variants("en", "check")), english


def test_dialogue_advances_only_on_agreement():
    dialogue = _dialogue()
    dialogue.opening()

    question = dialogue.respond("what does midpoint mean?")
    assert dialogue.step == 0  # a question never moves the lesson on
    assert question.endswith("?")

    confused = dialogue.respond("I don't understand")
    assert dialogue.step == 0  # neither does confusion

    dialogue.respond("yes, got it")
    assert dialogue.step == 1  # agreement is the only thing that advances


def test_repeated_confusion_never_repeats_itself():
    dialogue = _dialogue()
    dialogue.opening()
    first = dialogue.respond("I don't understand")
    second = dialogue.respond("no, still confused")
    assert first != second
    assert dialogue.step == 0


def test_walking_the_plan_ends_with_a_closing_line():
    dialogue = _dialogue()
    lines = [dialogue.opening()]
    guard = 0
    while dialogue.step < len(SECTIONS) - 1 and guard < 10:
        lines.append(dialogue.respond("yes"))
        guard += 1
    assert dialogue.step == len(SECTIONS) - 1
    closing = dialogue.respond("yes")
    assert "whole plan" in closing and closing.endswith("?")
    assert len(set(lines)) == len(lines)  # every step was taught once, in order


def test_language_switch_line_is_in_the_new_language_and_keeps_the_step():
    dialogue = _dialogue("en")
    dialogue.opening()
    dialogue.respond("yes")
    step_before = dialogue.step

    switched = TutorDialogue.from_metadata(
        {"topic_title": "Binary Search", "sections": SECTIONS}, "ar"
    )
    switched.step = step_before
    line = switched.language_switch()
    assert re.search(r"[\u0600-\u06FF]", line), line  # actually Arabic
    assert switched.step == step_before  # a switch is not a restart


def test_unplanned_dialogue_still_answers():
    dialogue = TutorDialogue.from_metadata(None, "en")
    assert not dialogue.planned
    assert dialogue.respond("yes").strip()
    assert dialogue.language_switch().strip()


def test_dialogue_resumes_at_the_reported_step():
    """A reconnected provider (failover / language change) is told where we are."""
    first = _dialogue("en")
    first.opening()
    first.respond("yes")
    first.respond("yes")
    position = first.step
    assert position >= 2, "two confirmations should have moved the lesson on"

    resumed = TutorDialogue.from_metadata(
        {"topic_title": "Binary Search", "sections": SECTIONS, "step_index": position}, "fr"
    )
    assert resumed.step == position
    # ... and it announces the step we are on, not step one again.
    line = resumed.language_switch()
    assert SECTIONS[position]["title"] in line
    assert SECTIONS[0]["title"] not in line


def test_step_index_is_clamped_and_optional():
    assert TutorDialogue.from_metadata({"sections": SECTIONS, "step_index": 99}, "en").step == len(SECTIONS) - 1
    assert TutorDialogue.from_metadata({"sections": SECTIONS, "step_index": -4}, "en").step == 0
    assert TutorDialogue.from_metadata({"sections": SECTIONS, "step_index": "2"}, "en").step == 2
    assert TutorDialogue.from_metadata({"sections": SECTIONS}, "en").step == 0
    assert TutorDialogue.from_metadata(None, "en").step == 0


# --------------------------------------------------------------------------- #
# variety — the thing that makes it sound human
# --------------------------------------------------------------------------- #


def test_every_repeated_line_has_alternatives_in_every_language():
    """One fixed sentence per situation is what sounds canned."""
    for language in LANGUAGES:
        for key in ("check", "praise", "rephrase", "encourage", "close"):
            variants = phrase_variants(language, key)
            assert len(variants) >= 2, f"{language}/{key}: {variants}"
            assert len(set(variants)) == len(variants), f"{language}/{key} repeats a variant"


def test_the_tutor_does_not_ask_a_question_after_every_step():
    """Teach, keep teaching, let the student interrupt — not step → quiz → step → quiz.

    Turns may legitimately end with an *invitation* ("what shall we look at next?"), so
    what is counted here is comprehension check-ins, not every question mark.
    """
    for language in ("en", "ar"):
        dialogue = _dialogue(language)
        turns = [dialogue.opening()]
        for _ in range(len(SECTIONS)):
            turns.append(dialogue.respond("yes"))

        def checks(turn: str) -> bool:
            return any(v in turn for v in phrase_variants(language, "check"))

        check_turns = [t for t in turns if checks(t)]
        teaching_without_a_question = [
            t for t in turns[1:] if not t.rstrip().endswith(("?", "؟"))
        ]
        assert not checks(turns[0]), "the opening must not quiz the student"
        assert len(check_turns) <= 1, f"{language}: {check_turns}"
        assert len(teaching_without_a_question) >= 1, turns
        # No comfort check-in anywhere: they were removed from the phrase tables' rotation
        # for exactly this complaint.
        assert not any("make sense so far" in t.lower() or "makes sense so far" in t.lower()
                       for t in turns)


def test_no_two_consecutive_turns_are_identical_and_variants_rotate():
    dialogue = _dialogue("ar")
    lines = [dialogue.opening()]
    for _ in range(5):
        lines.append(dialogue.respond("yes"))
        lines.append(dialogue.respond("لا أفهم"))
    for i in range(1, len(lines)):
        assert lines[i] != lines[i - 1], lines[i]
    # The praise line rotates rather than repeating one fixed sentence.
    assert len(phrase_variants("ar", "praise")) >= 2
    used = [v for v in phrase_variants("ar", "praise") if any(v in line for line in lines)]
    assert len(used) >= 2, f"only one praise variant was ever used: {used}"


def test_the_plan_is_closed_once_not_every_turn():
    dialogue = _dialogue("en")
    lines = [dialogue.opening()]
    for _ in range(len(SECTIONS) + 3):
        lines.append(dialogue.respond("yes"))
    closings = [l for l in lines if any(v in l for v in phrase_variants("en", "close"))]
    assert len(closings) == 1, closings
    assert dialogue.done is True
    # After the plan, the tutor hands the floor back instead of saying goodbye again.
    assert lines[-1].rstrip().endswith("?")


def test_a_second_confusion_uses_another_route_and_never_repeats():
    dialogue = _dialogue("en")
    dialogue.opening()
    first = dialogue.respond("I don't understand")
    second = dialogue.respond("still lost")
    third = dialogue.respond("no")
    assert len({first, second, third}) == 3
    assert dialogue.step == 0


def test_questions_are_still_answered_after_the_plan_is_finished():
    """Finishing the plan must not turn the tutor deaf: questions and confusion still work."""
    dialogue = _dialogue("en")
    dialogue.opening()
    for _ in range(len(SECTIONS)):
        dialogue.respond("yes")
    assert dialogue.done is True

    answered = dialogue.respond("what is a stack frame?")
    assert any(v in answered for v in phrase_variants("en", "answer_ack")), answered
    assert any(v in answered for v in phrase_variants("en", "invite")), answered

    confused = dialogue.respond("no, I don't understand")
    assert any(v in confused for v in phrase_variants("en", "rephrase")), confused
    assert dialogue.step == len(SECTIONS), "nothing left to advance to"


# --------------------------------------------------------------------------- #
# how it *sounds*: sentences, not plan formatting
# --------------------------------------------------------------------------- #


def test_spoken_steps_are_sentences_in_every_language():
    """A plan entry is a note; the spoken form must not read as one.

    No "Step 2:" labels, no " — " recitation, and the content still present.
    """
    title, goal = "Choosing the midpoint", "mid = (low + high) // 2"
    for language in LANGUAGES:
        for index in range(4):
            line = step_lead(language, title, goal, index)
            assert line.strip(), (language, index)
            assert not line.lstrip().lower().startswith(("step ", "step:", "next:")), line
            assert " — " not in line, line
            assert "," not in line[:2] or language != "en", line
            assert title.lower() in line.lower(), line
            assert "mid" in line.lower(), line


def test_spoken_leads_rotate_so_consecutive_steps_differ():
    seen = {step_lead("en", "Choosing the midpoint", "mid = (low + high) // 2", i) for i in range(4)}
    assert len(seen) >= 3, seen
    assert len({move_on("en", i) for i in range(3)}) == 3
    assert len({react("en", i) for i in range(4)}) == 4


@pytest.mark.parametrize(
    "written,spoken",
    [
        ("mid = (low + high) // 2", "mid equals low plus high divided by 2"),
        ("n >= 100", "n greater than or equal to 100"),
        ("O(n log n) comparisons", "On log n comparisons"),
        ("first — then", "first, then"),
        ("array[i] -> value", "arrayi becomes value"),
    ],
)
def test_speakable_turns_written_maths_into_words(written, spoken):
    """The synthesiser must not announce punctuation names or read "//" as a URL."""
    out = speakable(written)
    assert out == spoken, out
    for smell in ("//", "—", "->", "(", ")"):
        assert smell not in out, out


def test_every_language_has_every_spoken_helper():
    from app.prompts.interaction import MOVE_ON, REACT, STEP_LEAD

    for language in LANGUAGES:
        assert len(STEP_LEAD[language]) >= 3, language
        assert len(MOVE_ON[language]) >= 3, language
        assert len(REACT[language]) >= 3, language
        assert len(phrase_variants(language, "holding")) >= 1, language
        assert len(phrase_variants(language, "which_part")) >= 1, language


def test_the_mock_never_reads_a_label_or_an_em_dash_aloud():
    """End to end through the dialogue: nothing that only makes sense on paper."""
    for language in ("en", "ar", "zu"):
        dialogue = _dialogue(language)
        lines = [dialogue.opening()]
        for said in ("mhm", "yes", "I don't understand", "yes", "yes", "yes"):
            lines.append(dialogue.respond(said))
        for line in lines:
            assert "Step one" not in line and "Step 1" not in line, line
            assert "Next:" not in line, line
            # Whatever punctuation the transcript carries, what reaches the speaker is
            # clean: dashes become pauses and "//" becomes words.
            spoken = speakable(line)
            assert "—" not in spoken and "//" not in spoken, spoken
            assert "(" not in spoken and ")" not in spoken, spoken
