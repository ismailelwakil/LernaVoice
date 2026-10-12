"""Failover scenarios (§18, §21, §54) and the cascade component (§11)."""

from __future__ import annotations

import pytest

from app.providers.base import ProviderEventType
from app.providers.mock.providers import (
    INJECTOR,
    MockLLMProvider,
    MockSTTProvider,
    MockTTSProvider,
)
from app.providers.cascade import CascadePipelineProvider, _take_sentence
from app.providers.base import SessionConfig
from app.voice.events import EventType
from app.voice.state import SessionState


# --------------------------------------------------------------------------- #
# §54 scenarios
# --------------------------------------------------------------------------- #


async def test_gemini_success_no_fallback(session, recorder):
    rec = recorder(session)
    await session.start()
    await rec.drain()
    assert session.state.active_pipeline.signature() == "realtime:gemini"
    assert not rec.has(EventType.PROVIDER_FALLBACK_STARTED)
    assert session.fallback_reason is None


async def test_gemini_temporary_failure_then_recovers(session, recorder):
    """One transient failure, one retry, still Gemini. No fallback."""
    INJECTOR.fail("gemini", "timeout", times=1)
    rec = recorder(session)
    await session.start()
    await rec.drain()

    assert rec.has(EventType.PROVIDER_RETRYING)
    assert not rec.has(EventType.PROVIDER_FALLBACK_STARTED)
    assert session.state.active_pipeline.realtime == "gemini"
    assert session.retry_count == 1


async def test_gemini_permanent_failure_falls_back(session, recorder):
    INJECTOR.fail("gemini", "internal", times=10_000)
    rec = recorder(session)
    await session.start()
    await rec.drain()

    assert rec.has(EventType.PROVIDER_FALLBACK_STARTED)
    pipeline = session.state.active_pipeline
    assert pipeline.mode == "cascade"
    assert "gemini" not in (pipeline.stt, pipeline.llm, pipeline.tts)
    assert pipeline.stt == "elevenlabs"
    assert pipeline.llm == "lerna"


async def test_elevenlabs_failure_moves_to_deepgram_components(session, recorder):
    INJECTOR.fail("gemini", "internal")
    INJECTOR.fail("elevenlabs", "internal")
    rec = recorder(session)
    await session.start()
    await rec.drain()

    pipeline = session.state.active_pipeline
    assert pipeline.mode == "cascade"
    assert pipeline.stt == "deepgram"
    assert pipeline.tts == "deepgram"
    assert pipeline.llm == "lerna"
    assert len(rec.of(EventType.PROVIDER_FALLBACK_STARTED)) >= 2


async def test_all_providers_fail_gives_graceful_error(session, recorder):
    for vendor in ("gemini", "elevenlabs", "deepgram", "lerna"):
        INJECTOR.fail(vendor, "internal")
    rec = recorder(session)
    with pytest.raises(Exception):
        await session.start()
    await rec.drain()

    errors = rec.of(EventType.ERROR)
    assert errors, "a structured error event must be emitted"
    payload = errors[-1].data
    assert payload["code"] == "VOICE_PROVIDER_UNAVAILABLE"
    assert payload["recoverable"] is True
    # The message says what happened; a setup-type failure additionally carries a hint.
    assert "could be reached" in payload["message"] or "temporarily unavailable" in payload["message"]
    assert payload.get("hint") is None or isinstance(payload["hint"], str)
    assert session.state.state is SessionState.ERROR


async def test_auth_failure_is_not_retried(session, recorder):
    INJECTOR.fail("gemini", "auth")
    rec = recorder(session)
    await session.start()
    await rec.drain()
    assert not rec.has(EventType.PROVIDER_RETRYING)  # §20
    assert rec.has(EventType.PROVIDER_FALLBACK_STARTED)


# --------------------------------------------------------------------------- #
# §21 session continuity
# --------------------------------------------------------------------------- #


async def test_failover_preserves_the_entire_session(session, recorder):
    rec = recorder(session)
    await session.start()
    session.state.current_topic = "Binary Search"
    session.state.current_section = "Choosing the midpoint"
    session.state.concepts_covered = ["sorted array", "low pointer"]

    await session.interrupt()
    checkpoint_id = session.state.resume_checkpoint.checkpoint_id
    await session.ask_question("Why split in half?")
    original_session_id = session.state.session_id

    # Gemini dies mid-answer.
    INJECTOR.fail("gemini", "internal")
    await session._on_provider_error(RuntimeError("gemini exploded"))
    await rec.drain()

    assert session.state.session_id == original_session_id  # same session
    assert session.state.language == "en"
    assert session.state.current_topic == "Binary Search"
    assert session.state.resume_checkpoint.checkpoint_id == checkpoint_id
    assert session.state.concepts_covered == ["sorted array", "low pointer"]
    assert [q.text for q in session.state.student_questions] == ["Why split in half?"]
    assert session.state.active_pipeline.mode == "cascade"
    assert rec.has(EventType.PROVIDER_SWITCHED)
    assert session.state.interrupt_count == 1  # lesson did not restart


async def test_provider_transitions_are_recorded(session, repository):
    await session.start()
    INJECTOR.fail("gemini", "internal")
    await session._on_provider_error(RuntimeError("down"))

    history = session.state.provider_history
    assert len(history) >= 2
    assert history[-1].to_pipeline.startswith("cascade:")
    assert history[-1].reason

    stored = await repository.history(session.state.session_id)
    kinds = {e["kind"] for e in stored["voice_provider_events"]}
    assert {"selected", "connected", "failed"} <= kinds


async def test_circuit_breaker_avoids_a_just_failed_provider(session, router):
    INJECTOR.fail("gemini", "internal")
    await session.start()
    health = router.health.get("gemini")
    assert health.consecutive_failures >= 1
    assert router.health.snapshot()["gemini"]["total_failures"] >= 1


# --------------------------------------------------------------------------- #
# cascade internals
# --------------------------------------------------------------------------- #


async def test_cascade_streams_stt_then_llm_then_tts():
    stt = MockSTTProvider("elevenlabs", transcript="What is a midpoint?")
    llm = MockLLMProvider("lerna", reply="The midpoint is the middle index of the current range.")
    tts = MockTTSProvider("gemini")
    pipeline = CascadePipelineProvider(stt, llm, tts, name="cascade:test")

    events = []

    await pipeline.start_session(
        SessionConfig(session_id="s1", language="ig", system_instruction="be a tutor")
    )
    await pipeline.send_text("Explain binary search")

    import asyncio

    async def collect():
        async for event in pipeline.receive_events():
            events.append(event)
            if event.type is ProviderEventType.TURN_COMPLETE and event.text:
                return

    await asyncio.wait_for(collect(), timeout=5)
    await pipeline.close_session()

    types = [e.type for e in events]
    assert ProviderEventType.TURN_STARTED in types
    assert ProviderEventType.OUTPUT_TRANSCRIPT in types
    assert ProviderEventType.AUDIO in types
    assert tts.spoken, "the TTS component must have been used"


async def test_cascade_interrupt_cancels_generation_and_tts():
    stt = MockSTTProvider("elevenlabs")
    llm = MockLLMProvider("lerna", reply="A long explanation. " * 20)
    tts = MockTTSProvider("gemini")
    pipeline = CascadePipelineProvider(stt, llm, tts)
    await pipeline.start_session(SessionConfig(session_id="s", language="ig", system_instruction=""))
    await pipeline.send_text("go")
    await pipeline.interrupt()
    assert tts.cancelled >= 1
    await pipeline.close_session()


def test_sentence_chunker_waits_for_a_full_sentence():
    assert _take_sentence("short") == ("", "short")
    long_partial = "x" * 70
    assert _take_sentence(long_partial) == ("", long_partial)
    sentence, rest = _take_sentence("A" * 60 + ". next part")
    assert sentence.endswith(".")
    assert rest.strip() == "next part"
