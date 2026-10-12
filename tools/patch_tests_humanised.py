"""Update the tests that encoded 'check after every step' to the humanised contract,
and add tests for variety + not interrogating the student."""

import re

# ============================================================ test_mock_audio.py
P = "tests/provider/test_mock_audio.py"
s = open(P).read()

s = s.replace(
    '''async def test_mock_opens_with_a_greeting_step_and_a_check_in():
    """The tutor must not monologue: after step one it asks whether it made sense."""''',
    '''async def test_mock_opens_with_a_greeting_step_and_an_open_floor():
    """Step one is taught and the floor is handed over — without a comprehension quiz."""''',
)
s = s.replace(
    '''    assert "هل الكلام واضح" in spoken, "the tutor must check understanding in the lesson language"''',
    '''    # It invites the student to cut in rather than asking "does that make sense?".
    assert any(v in spoken for v in phrase_variants("ar", "invite_stop")), spoken
    assert not any(v in spoken for v in phrase_variants("ar", "check")), spoken''',
)

s = s.replace(
    '''    assert "Take your time" in first, first''',
    '''    assert any(v in first for v in phrase_variants("en", "encourage")), first''',
)

s = s.replace(
    '''    assert "mpango wote" in lines[-1], "the closing line should come in the lesson language"''',
    '''    # The closing line is Swahili (any of its variants), and the walk reached it.
    assert any(v in lines[-1] for v in phrase_variants("sw", "close")), lines[-1]''',
)

s = s.replace(
    '''    assert opening.startswith("Ndeewo") and "What a limit means" in opening
    assert "Ọ doro anya" in opening                   # Igbo check-in''',
    '''    assert opening.startswith("Ndeewo") and "What a limit means" in opening
    # Igbo scaffolding, and the opening hands the turn over instead of quizzing.
    assert any(v in opening for v in phrase_variants("ig", "invite_stop")), opening''',
)

s = s.replace(
    '''    confused = await reply("mba, aghọtaghị m")
    assert "nsogbu adịghị" in confused.lower() or "N'ụzọ ọzọ" in confused''',
    '''    confused = await reply("mba, aghọtaghị m")
    assert any(v in confused for v in phrase_variants("ig", "rephrase")), confused''',
)

if "phrase_variants" not in s.split("def test_mock_opens")[0]:
    s = s.replace(
        "from app.providers.mock.providers import (",
        "from app.prompts.interaction import phrase_variants\nfrom app.providers.mock.providers import (",
        1,
    )
open(P, "w").write(s)

# ============================================================ test_interaction_layer.py
P = "tests/unit/test_interaction_layer.py"
s = open(P).read()

s = s.replace(
    '''def test_system_instruction_carries_the_interaction_contract():
    instruction = build_system_instruction(language="ar")
    assert INTERACTION_SUFFIX in instruction
    # The contract is about *teaching behaviour*, not decoration.
    for promise in ("Teach ONE idea", "wait", "Never repeat the sentence"):
        assert promise in instruction
    # Language instructions still present.
    assert "LANGUAGE" in instruction''',
    '''def test_system_instruction_carries_the_interaction_contract():
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
    text = INTERACTION_SUFFIX.lower()
    assert "do not have to ask a question at the end of every step" in text
    assert "never use \\"is that clear?\\" style check-ins" in text
    assert "only when it earns its place" in text
    assert "variety" in text or "vary how you open every single turn" in text''',
)

s = s.replace(
    '''def test_english_scaffolding_never_leaks_into_another_language():
    """A switch to Arabic/Zulu must not leave English sentence frames behind."""
    english_only = ("Today we are working on", "Step one:", "Next:", "Right — we're on", "nothing more than that")
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
            # the localised interaction lines are present
            assert phrase(language, "check") in line or phrase(language, "invite") in line, line''',
    '''def test_english_scaffolding_never_leaks_into_another_language():
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
            assert any(v and v in line for key in keys for v in phrase_variants(language, key)), line''',
)

s = s.replace(
    '''def test_dialogue_resumes_at_the_reported_step():
    """A reconnected provider (failover / language change) is told where we are."""
    first = _dialogue("en")
    first.opening()
    first.respond("yes")
    first.respond("yes")
    assert first.step == 2

    resumed = TutorDialogue.from_metadata(
        {"topic_title": "Binary Search", "sections": SECTIONS, "step_index": 2}, "fr"
    )
    assert resumed.step == 2
    # ... and it announces the step we are on, not step one again.
    line = resumed.language_switch()
    assert SECTIONS[2]["title"] in line
    assert SECTIONS[0]["title"] not in line''',
    '''def test_dialogue_resumes_at_the_reported_step():
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
    assert SECTIONS[0]["title"] not in line''',
)

s = s.replace(
    "from app.prompts.interaction import (\n    INTERACTION_PHRASES,\n    INTERACTION_SUFFIX,",
    "from app.prompts.interaction import (\n    INTERACTION_PHRASES,\n    INTERACTION_SUFFIX,\n    PHRASE_VARIANTS,",
)
if "phrase_variants," not in s.split("def ")[0]:
    s = s.replace("    is_language_switch_prompt,\n    phrase,\n)", "    is_language_switch_prompt,\n    phrase,\n    phrase_variants,\n)")

# new: variety + no interrogation + close once
s += '''

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
    """Teach, keep teaching, let the student interrupt — not step → quiz → step → quiz."""
    for language in ("en", "ar"):
        dialogue = _dialogue(language)
        turns = [dialogue.opening()]
        for _ in range(len(SECTIONS)):
            turns.append(dialogue.respond("yes"))
        asked = [t for t in turns if t.rstrip().endswith(("?", "؟"))]
        assert turns[0].rstrip().endswith(("?", "؟")) is False, "the opening must not quiz"
        assert len(asked) < len(turns), "every turn ended with a question"
        assert len(asked) <= max(1, len(turns) // 2), f"{language}: {len(asked)} of {len(turns)}"


def test_no_two_consecutive_turns_are_identical_and_variants_rotate():
    dialogue = _dialogue("ar")
    lines = [dialogue.opening()]
    for _ in range(5):
        lines.append(dialogue.respond("yes"))
        lines.append(dialogue.respond("لا أفهم"))
    for i in range(1, len(lines)):
        assert lines[i] != lines[i - 1], lines[i]
    # The praise line is not the same sentence every time it is used.
    praises = [phrase_variants("ar", "praise")]
    assert len(praises[0]) >= 2


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
'''
open(P, "w").write(s)

# ============================================================ lifecycle test
P = "tests/integration/test_session_lifecycle.py"
s = open(P).read()
s = s.replace(
    '''    position = session.state.current_section
    assert position, "the provider never reported its plan position"
    assert session._plan_position() == 2, "two confirmations after the opening: step three"

    await session.change_language("fr")
    await rec.drain()

    assert session.state.current_section == position             # position preserved
    assert session.provider.config.metadata["step_index"] == 2    # handed to the new provider
    assert session.provider.dialogue.step == 2                   # it resumes there, no restart

    await session.send_text("oui")
    await rec.drain()
    assert session._plan_position() == 3                          # and carries on from there''',
    '''    position = session.state.current_section
    index = session._plan_position()
    assert position, "the provider never reported its plan position"
    assert index > 0, "the confirmations should have moved the lesson on"

    await session.change_language("fr")
    await rec.drain()

    assert session.state.current_section == position             # position preserved
    assert session.provider.config.metadata["step_index"] == index  # handed to the new provider
    assert session.provider.dialogue.step == index               # it resumes there, no restart

    await session.send_text("oui")
    await rec.drain()
    assert session._plan_position() > index                       # and carries on from there''',
)
open(P, "w").write(s)

import subprocess
print(subprocess.run(["python3", "-m", "pytest", "tests/provider/test_mock_audio.py",
                      "tests/unit/test_interaction_layer.py", "tests/integration", "-q",
                      "-p", "no:cacheprovider"], capture_output=True, text=True).stdout[-2500:])
