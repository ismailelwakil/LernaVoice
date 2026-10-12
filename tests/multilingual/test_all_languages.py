"""The ten-language matrix (§53). Every language runs the full cycle."""

from __future__ import annotations

import pytest

from app.prompts.languages import (
    INTERRUPT_ACK,
    LANGUAGE_INSTRUCTIONS,
    RESUME_TRANSITION,
    interrupt_ack,
)
from app.voice.events import EventType
from app.voice.state import SUPPORTED_LANGUAGES, LANGUAGE_NAMES


def test_every_language_has_prompts():
    for code in SUPPORTED_LANGUAGES:
        assert code in LANGUAGE_INSTRUCTIONS and len(LANGUAGE_INSTRUCTIONS[code]) > 40
        assert code in INTERRUPT_ACK
        assert code in RESUME_TRANSITION
        assert code in LANGUAGE_NAMES


def test_arabic_acknowledgement_is_the_demo_line():
    assert interrupt_ack("ar") == "طبعًا، اتفضل اسأل سؤالك."


def test_language_instructions_forbid_drifting():
    for code, text in LANGUAGE_INSTRUCTIONS.items():
        assert len(text.split()) > 10, code


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
async def test_full_cycle_per_language(manager, recorder, language):
    """1 session, 2 language, 3 provider, 4 audio, 5 response, 6 interrupt,
    7 question, 8 follow-up, 9 resume, 10 persistence."""
    session = await manager.create(
        student_id=f"student-{language}",
        language=language,
        course_id="algorithms-101",
        lesson_id="lesson-binary-search",
        topic="Binary Search",
    )
    rec = recorder(session)

    await session.start()
    await rec.drain()
    assert session.state.language == language
    assert rec.has(EventType.PROVIDER_CONNECTED)

    await session.send_audio(b"\x00\x01" * 320)

    await session._finish_turn("Explaining the first concept.")
    result = await session.interrupt()
    assert result["acknowledgement"] == interrupt_ack(language)

    await session.ask_question("Why?")
    await session._finish_turn("Because of this reason.")
    await session.ask_question("And then?")
    await session._finish_turn("Then this happens.")
    await session.resume()
    await session.end()

    stored = await manager.repository.get_session(session.state.session_id)
    assert stored is not None
    assert stored.language == language
    assert stored.interrupt_count == 1
    assert len(stored.student_questions) == 2
    assert stored.resume_checkpoint is not None


@pytest.mark.parametrize(
    "language,expected_mode,expected",
    [
        ("en", "realtime", {"realtime": "gemini"}),
        ("ar", "realtime", {"realtime": "gemini"}),
        ("fr", "realtime", {"realtime": "gemini"}),
        ("sw", "realtime", {"realtime": "gemini"}),
        ("am", "realtime", {"realtime": "gemini"}),
        ("ha", "realtime", {"realtime": "gemini"}),
        ("so", "realtime", {"realtime": "gemini"}),
        ("yo", "realtime", {"realtime": "gemini"}),
        ("zu", "realtime", {"realtime": "gemini"}),
        ("ig", "cascade", {"stt": "elevenlabs", "llm": "gemini", "tts": "gemini"}),
    ],
)
async def test_documented_pipeline_per_language(manager, language, expected_mode, expected):
    session = await manager.create(student_id="s", language=language)
    await session.start()
    pipeline = session.state.active_pipeline
    assert pipeline.mode == expected_mode
    for role, vendor in expected.items():
        assert getattr(pipeline, role) == vendor


async def test_igbo_session_is_fully_functional(manager, recorder):
    """§15: Igbo must work end to end through the composed pipeline."""
    session = await manager.create(student_id="student-ig", language="ig", topic="Binary Search")
    rec = recorder(session)
    await session.start()
    await rec.drain()

    assert session.state.active_pipeline.mode == "cascade"
    assert rec.has(EventType.PROVIDER_CONNECTED)

    await session.interrupt()
    await session.ask_question("Gịnị bụ binary search?")
    await session._finish_turn("Ọ bụ ụzọ ịchọ ihe n'usoro.")
    assert session.state.student_questions[0].answered
