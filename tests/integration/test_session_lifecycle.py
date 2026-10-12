"""Session, checkpoint, interruption, follow-ups and smart resume (§21-§28)."""

from __future__ import annotations

import pytest

from app.voice.events import EventType
from app.voice.interruption_manager import InterruptionManager
from app.voice.resume_manager import ResumeManager
from app.voice.state import SessionState


async def _started(session, recorder):
    rec = recorder(session)
    await session.start()
    await rec.drain()
    return rec


async def test_session_starts_on_gemini_realtime(session, recorder):
    rec = await _started(session, recorder)
    assert rec.has(EventType.SESSION_STARTED)
    assert rec.has(EventType.PROVIDER_SELECTED)
    assert rec.has(EventType.PROVIDER_CONNECTED)
    assert session.state.active_pipeline.signature() == "realtime:gemini"


async def test_interrupt_stops_playback_before_anything_else(session, recorder):
    rec = await _started(session, recorder)
    await session.interrupt()
    await rec.drain()

    interrupted = rec.of(EventType.ASSISTANT_INTERRUPTED)
    checkpoints = rec.of(EventType.CHECKPOINT_CREATED)
    assert interrupted and checkpoints
    assert interrupted[0].data["stop_playback"] is True
    # §23: the stop event must precede the checkpoint work.
    assert interrupted[0].seq < checkpoints[0].seq
    assert session.state.state is SessionState.INTERRUPTED


async def test_interrupt_creates_a_learning_checkpoint(session, recorder):
    rec = await _started(session, recorder)
    session.state.current_topic = "Binary Search"
    session.state.current_section = "Choosing the midpoint"
    session.state.concepts_covered = ["sorted array", "low pointer", "high pointer"]

    result = await session.interrupt()
    checkpoint = result["checkpoint"]
    assert checkpoint["topic"] == "Binary Search"
    assert checkpoint["section"] == "Choosing the midpoint"
    assert "low pointer" in checkpoint["concepts_covered"]
    assert checkpoint["resume_instruction"]
    assert session.state.resume_checkpoint is not None


async def test_question_then_followup_then_resume(session, recorder, rag):
    rec = await _started(session, recorder)
    manager = InterruptionManager(session)
    await manager.interrupt()

    first = await manager.ask("Why do we split the array in half?")
    assert first["is_followup"] is False
    await rec.drain()
    await session._finish_turn("Because halving removes half the candidates each step.")

    followup = await manager.ask("And what if the array is not sorted?")
    assert followup["is_followup"] is True
    await session._finish_turn("Then binary search is not valid at all.")

    assert len(session.state.student_questions) == 2
    assert all(q.answered for q in session.state.student_questions)
    assert rag.queries  # RAG was consulted

    await rec.drain()
    await ResumeManager(session).resume()
    await rec.drain()
    assert rec.has(EventType.RESUME_STARTED)
    assert rec.has(EventType.RESUME_COMPLETED)
    assert session.state.resume_count == 1


async def test_multiple_interruption_cycles(session, recorder):
    """§25: unlimited cycles, checkpoint updated every time."""
    rec = await _started(session, recorder)
    manager = InterruptionManager(session)
    checkpoint_ids = []

    for i in range(4):
        session.state.concepts_covered.append(f"concept-{i}")
        await manager.interrupt()
        checkpoint_ids.append(session.state.resume_checkpoint.checkpoint_id)
        await manager.ask(f"Question number {i}?")
        await session._finish_turn(f"Answer number {i}.")
        await ResumeManager(session).resume()

    assert session.state.interrupt_count == 4
    assert session.state.resume_count == 4
    assert len(set(checkpoint_ids)) == 4  # a fresh checkpoint per interruption
    assert len(session.state.student_questions) == 4
    assert not session.state.unresolved_questions


async def test_resume_does_not_restart_the_lesson(session, recorder):
    await _started(session, recorder)
    session.state.concepts_covered = ["sorted array", "midpoint calculation"]
    await session.interrupt()
    await session.resume()

    provider = session.provider
    resume_prompt = provider.sent_text[-1]
    assert "continue" in resume_prompt.lower()
    assert "do not repeat" in resume_prompt.lower() or "Already covered" in resume_prompt
    assert "sorted array" in resume_prompt


async def test_tool_calls_drive_visuals_and_learning_signals(session, recorder, progress):
    rec = await _started(session, recorder)

    await session._handle_tool("show_visual", {"type": "equation", "content": "mid = (low + high) // 2"})
    await session._handle_tool(
        "record_learning_signal", {"kind": "misconception_detected", "concept": "unsorted binary search"}
    )
    await session._handle_tool(
        "update_lesson_position", {"topic": "Binary Search", "section": "Comparison step"}
    )
    await rec.drain()

    visual = rec.of(EventType.VISUAL_UPDATED)[0]
    assert visual.data["visual"]["type"] == "equation"
    assert "unsorted binary search" in session.state.misconceptions
    assert progress.signals  # forwarded to the LERNA Progress Profile
    assert session.state.current_section == "Comparison step"


async def test_language_change_preserves_the_checkpoint(session, recorder):
    await _started(session, recorder)
    session.state.concepts_covered = ["sorted array"]
    await session.interrupt()
    checkpoint_id = session.state.resume_checkpoint.checkpoint_id

    result = await session.change_language("ar")
    assert result["changed"] is True
    assert session.state.language == "ar"
    assert session.state.resume_checkpoint.checkpoint_id == checkpoint_id
    assert session.state.concepts_covered == ["sorted array"]


def _spoken_after(rec, seq: int) -> str:
    """Everything the tutor said after a given event sequence number."""
    return " ".join(
        e.data.get("text", "") for e in rec.of(EventType.ASSISTANT_TEXT_DELTA) if e.seq > seq
    )


async def test_language_change_is_spoken_in_the_new_language(dialogue_session, recorder):
    """A switch that produces no audio leaves the student hearing the old language."""
    session = dialogue_session
    rec = await _started(session, recorder)
    session.state.concepts_covered = ["sorted order"]
    await session.interrupt()
    await rec.drain()

    before = rec.last_seq
    result = await session.change_language("ar")
    await rec.drain()

    assert result["changed"] is True and session.state.language == "ar"
    spoken = _spoken_after(rec, before)
    assert spoken.strip(), "the language change produced no speech"
    # The tutor answers in Arabic (the mock's Arabic interaction lines) — not English.
    assert any("\u0600" <= ch <= "\u06FF" for ch in spoken), spoken
    # And the lesson continues from where it stopped instead of restarting.
    assert session.state.concepts_covered == ["sorted order"]
    assert session.state.current_section


async def test_the_lesson_position_survives_a_language_change(dialogue_session, recorder):
    """The mock reports its step through `update_lesson_position`; the reconnect
    hands it back as `step_index`, so a switch resumes instead of restarting."""
    session = dialogue_session
    rec = await _started(session, recorder)
    for _ in range(2):
        await session.send_text("yes")
    await rec.drain()

    position = session.state.current_section
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
    after = session._plan_position()
    assert after >= index, "the lesson went backwards after the switch"
    if index < len(session.state.lesson_plan) - 1:
        assert after > index, "there was room to advance and it did not"


async def test_language_change_emits_the_event_and_reaches_provider_state(dialogue_session, recorder):
    session = dialogue_session
    rec = await _started(session, recorder)
    await rec.drain()

    await session.change_language("sw")
    await rec.drain()

    changed = rec.of(EventType.LANGUAGE_CHANGED)[-1]
    assert changed.data["from"] == "en" and changed.data["to"] == "sw"
    assert changed.data["pipeline"]["realtime"] or changed.data["pipeline"]["stt"]
    # The mock provider was rebuilt for the new language, not reused.
    assert session.provider.config.language == "sw"
    assert "Swahili" in session.provider.config.system_instruction


async def test_pause_and_end(session, recorder):
    rec = await _started(session, recorder)
    await session.pause()
    assert session.state.state is SessionState.PAUSED
    await session.end()
    await rec.drain()
    assert session.state.state is SessionState.ENDED
    assert rec.has(EventType.SESSION_ENDED)
    assert session.state.session_summary


async def test_malformed_audio_is_rejected(session, recorder):
    await _started(session, recorder)
    from app.providers.base import MalformedAudioError

    with pytest.raises(MalformedAudioError):
        await session.send_audio(b"\x00\x01\x02")  # odd number of bytes
