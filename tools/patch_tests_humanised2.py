"""Fix the remaining test expectations after the humanisation change."""

# ---------------------------------------------------------------- interaction layer tests
P = "tests/unit/test_interaction_layer.py"
s = open(P).read()

s = s.replace(
    '''    text = INTERACTION_SUFFIX.lower()
    assert "do not have to ask a question at the end of every step" in text
    assert "never use \\"is that clear?\\" style check-ins" in text
    assert "only when it earns its place" in text
    assert "variety" in text or "vary how you open every single turn" in text''',
    '''    text = " ".join(INTERACTION_SUFFIX.lower().split())  # rules span lines in the source
    assert "do not have to ask a question at the end of every step" in text
    assert "never use \\"is that clear?\\" style check-ins" in text
    assert "only when it earns its place" in text
    assert "vary how you open every single turn" in text
    assert "never reuse a sentence" in text''',
)

s = s.replace(
    '''    english = _dialogue().opening()
    assert "Binary Search" in english
    assert "?" in english  # it stops and checks''',
    '''    english = _dialogue().opening()
    assert "Binary Search" in english
    # It hands the floor over rather than checking comprehension on turn one.
    assert any(v in english for v in phrase_variants("en", "invite_stop")), english
    assert not any(v in english for v in phrase_variants("en", "check")), english''',
)

s = s.replace(
    '''def test_the_tutor_does_not_ask_a_question_after_every_step():
    """Teach, keep teaching, let the student interrupt — not step → quiz → step → quiz."""
    for language in ("en", "ar"):
        dialogue = _dialogue(language)
        turns = [dialogue.opening()]
        for _ in range(len(SECTIONS)):
            turns.append(dialogue.respond("yes"))
        asked = [t for t in turns if t.rstrip().endswith(("?", "؟"))]
        assert turns[0].rstrip().endswith(("?", "؟")) is False, "the opening must not quiz"
        assert len(asked) < len(turns), "every turn ended with a question"
        assert len(asked) <= max(1, len(turns) // 2), f"{language}: {len(asked)} of {len(turns)}"''',
    '''def test_the_tutor_does_not_ask_a_question_after_every_step():
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
                       for t in turns)''',
)

s = s.replace(
    '''    for i in range(1, len(lines)):
        assert lines[i] != lines[i - 1], lines[i]
    # The praise line is not the same sentence every time it is used.
    praises = [phrase_variants("ar", "praise")]
    assert len(praises[0]) >= 2''',
    '''    for i in range(1, len(lines)):
        assert lines[i] != lines[i - 1], lines[i]
    # The praise line rotates rather than repeating one fixed sentence.
    assert len(phrase_variants("ar", "praise")) >= 2
    used = [v for v in phrase_variants("ar", "praise") if any(v in line for line in lines)]
    assert len(used) >= 2, f"only one praise variant was ever used: {used}"''',
)
open(P, "w").write(s)

# ---------------------------------------------------------------- mock audio tests
P = "tests/provider/test_mock_audio.py"
s = open(P).read()
s = s.replace('    assert "Take your time" in first_no',
              '    assert any(v in first_no for v in phrase_variants("en", "encourage")), first_no')
s = s.replace(
    '''    # The closing line is Swahili (any of its variants), and the walk reached it.
    assert any(v in lines[-1] for v in phrase_variants("sw", "close")), lines[-1]''',
    '''    # The walk reached a Swahili closing line (it may be in any of its variants, and
    # the merged turns mean it can arrive earlier than the raw section count).
    assert any(any(v in line for v in phrase_variants("sw", "close")) for line in lines), lines''',
)
open(P, "w").write(s)

# ---------------------------------------------------------------- lifecycle test
P = "tests/integration/test_session_lifecycle.py"
s = open(P).read()
s = s.replace(
    '''    await session.send_text("oui")
    await rec.drain()
    assert session._plan_position() > index                       # and carries on from there''',
    '''    await session.send_text("oui")
    await rec.drain()
    after = session._plan_position()
    assert after >= index, "the lesson went backwards after the switch"
    if index < len(session.state.lesson_plan) - 1:
        assert after > index, "there was room to advance and it did not"''',
)
open(P, "w").write(s)

import subprocess
print(subprocess.run(["python3", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
                     capture_output=True, text=True).stdout[-1800:])
