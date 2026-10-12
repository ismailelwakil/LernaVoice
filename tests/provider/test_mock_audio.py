"""Mock-provider audio behaviour (§52).

The mock vendors are what the offline demo and every test run on, so their
audio has to behave like a real vendor: audible samples, a reply long enough to
listen to, streamed in chunks, and turn-taking driven by a pause rather than a
byte counter. These tests guard the demo path a human actually listens to.

No credentials, no network.
"""

from __future__ import annotations

import asyncio
import math
import struct

import pytest

from app.providers.base import AudioChunk, ProviderEventType, SessionConfig
from app.providers.mock.dialogue import TutorDialogue
from app.prompts.interaction import phrase_variants
from app.providers.mock.providers import (
    MockLLMProvider,
    MockRealtimeProvider,
    MockTTSProvider,
    _chunks,
    _voice_pcm,
    utterance_ms,
)

FRAME = 1600  # bytes of PCM16 @ 16 kHz == 0.1 s of input audio
AUDIBLE_PEAK = 4000  # the old DC-offset mock peaked at 256


def _stats(pcm: bytes) -> tuple[int, float]:
    samples = struct.unpack(f"<{len(pcm)//2}h", pcm)
    peak = max(abs(s) for s in samples)
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    return peak, rms


def _queued(provider) -> list:
    return [e.type for e in list(provider._queue._queue)]  # noqa: SLF001


# --------------------------------------------------------------------------- #
# the generator
# --------------------------------------------------------------------------- #


def test_mock_voice_is_audible_not_a_dc_offset():
    """Regression: the old mock emitted b"\\x00\\x01" * n — a constant DC offset
    that plays as silence. The generator must produce a real waveform."""
    pcm = _voice_pcm(1000)
    peak, rms = _stats(pcm)
    assert peak > AUDIBLE_PEAK, f"peak amplitude too low to hear ({peak})"
    assert rms > 1200, f"rms too low to hear ({rms})"
    samples = struct.unpack(f"<{len(pcm)//2}h", pcm)
    crossings = sum(1 for a, b in zip(samples, samples[1:]) if (a < 0) != (b < 0))
    assert crossings > 200, f"signal never oscillates ({crossings} zero crossings)"


def test_mock_voice_is_deterministic_and_sized_in_milliseconds():
    assert _voice_pcm(500) == _voice_pcm(500)
    assert len(_voice_pcm(500)) == 24000 * 500 // 1000 * 2


def test_utterance_length_follows_the_text_being_spoken():
    short = utterance_ms("Yes.")
    long = utterance_ms("Let me walk you through binary search step by step. " * 3)
    assert 700 <= short < long <= 3200


def test_audio_is_streamed_in_multiple_chunks():
    """Chunked delivery is what exercises the client's incremental playback."""
    chunks = list(_chunks(_voice_pcm(1000)))
    assert len(chunks) > 3
    assert all(len(c.data) <= 24000 * 0.2 * 2 for c in chunks)  # <= 200 ms
    assert all(c.sample_rate == 24000 for c in chunks)


# --------------------------------------------------------------------------- #
# realtime provider turn behaviour
# --------------------------------------------------------------------------- #


async def _drain(provider, *, until=ProviderEventType.TURN_COMPLETE, timeout=5.0):
    events: list = []

    async def collect():
        async for event in provider.receive_events():
            events.append(event)
            if event.type is until:
                return

    await asyncio.wait_for(collect(), timeout=timeout)
    return events


@pytest.fixture
def realtime() -> MockRealtimeProvider:
    return MockRealtimeProvider("gemini", reply="Binary search halves the interval.")


async def test_text_turn_returns_streamed_audio_and_a_transcript(realtime):
    await realtime.start_session(SessionConfig(session_id="s", language="en", system_instruction=""))
    await realtime.send_text("hello")
    events = await _drain(realtime)

    types = [e.type for e in events]
    assert ProviderEventType.TURN_STARTED in types
    assert ProviderEventType.OUTPUT_TRANSCRIPT in types
    assert types[-1] is ProviderEventType.TURN_COMPLETE

    audio = [e.audio for e in events if e.type is ProviderEventType.AUDIO]
    assert len(audio) >= 5, "a reply must arrive as a stream, not one blob"
    total = sum(len(a) for a in audio)
    assert total >= 24000 * 0.7 * 2, f"reply audio too short to be useful ({total} bytes)"
    peak, _ = _stats(b"".join(audio))
    assert peak > AUDIBLE_PEAK, f"reply audio is inaudible (peak {peak})"


async def test_small_audio_frames_do_not_trigger_a_turn(realtime):
    """Guards the other suites: a stray PCM frame must not cause a reply."""
    await realtime.start_session(SessionConfig(session_id="s", language="en", system_instruction=""))
    while not realtime._queue.empty():  # drop the CONNECTED event
        realtime._queue.get_nowait()
    await realtime.send_audio(AudioChunk(data=b"\x12\x34" * 480, sample_rate=16000))
    await asyncio.sleep(0.9)
    assert _queued(realtime) == [], "a short frame must not look like an utterance"


async def test_silence_after_speech_ends_the_turn(realtime):
    """The mic path: speak, pause, and the mock 'hears' the student and answers."""
    realtime.vad_silence_s = 0.05
    await realtime.start_session(SessionConfig(session_id="s", language="en", system_instruction=""))
    for _ in range(10):  # 1 s of speech, past the 0.4 s VAD floor
        await realtime.send_audio(AudioChunk(data=b"\x11\x22" * (FRAME // 2), sample_rate=16000))

    events = await _drain(realtime)
    transcript = [e for e in events if e.type is ProviderEventType.INPUT_TRANSCRIPT and not e.partial]
    assert transcript, "the mock must 'hear' the student after the pause"
    assert transcript[-1].text == realtime.transcript
    assert any(e.type is ProviderEventType.AUDIO for e in events)


async def test_continuous_speech_yields_exactly_one_turn(realtime):
    """A long uninterrupted utterance must not produce a reply every N bytes."""
    realtime.vad_silence_s = 0.15
    await realtime.start_session(SessionConfig(session_id="s", language="en", system_instruction=""))
    for _ in range(25):  # 2.5 s of continuous speech
        await realtime.send_audio(AudioChunk(data=b"\x11\x22" * (FRAME // 2), sample_rate=16000))
        await asyncio.sleep(0.01)

    events = await _drain(realtime)
    finals = [e for e in events if e.type is ProviderEventType.INPUT_TRANSCRIPT and not e.partial]
    assert len(finals) == 1, f"expected one turn, got {len(finals)}"


# --------------------------------------------------------------------------- #
# teaching a catalogued lesson plan
# --------------------------------------------------------------------------- #


async def _turns(provider, student_lines: list[str]) -> list[tuple[str, bytes]]:
    """Send student turns and collect (spoken text, audio) for each."""
    out = []
    for line in student_lines:
        await provider.send_text(line)
        events = await _drain(provider)
        text = next(e.text for e in events if e.type is ProviderEventType.TURN_COMPLETE)
        audio = b"".join(e.audio for e in events if e.type is ProviderEventType.AUDIO)
        out.append((text, audio))
    return out


async def test_mock_opens_with_a_greeting_step_and_an_open_floor():
    """Step one is taught and the floor is handed over — without a comprehension quiz."""
    from app.curriculum import get_topic

    topic = get_topic("binary-search")
    provider = MockRealtimeProvider("gemini")
    await provider.start_session(
        SessionConfig(
            session_id="s",
            language="ar",
            system_instruction="",
            metadata={"topic_id": topic.id, "topic_title": topic.title,
                      "sections": topic.lesson_plan(), "student_name": "Mona"},
        )
    )
    (spoken, audio), = await _turns(provider, [""])

    assert spoken.startswith("مرحبًا بك"), f"expected an Arabic greeting, got: {spoken}"
    # Arabic sessions speak Arabic: the curated translation covers the demo topic, so
    # no English plan text leaks into an Arabic turn.
    assert "البحث الثنائي" in spoken and "فكرة التنصيف" in spoken
    assert "Binary Search" not in spoken and "The idea of halving" not in spoken
    # It invites the student to cut in rather than asking "does that make sense?".
    assert any(v in spoken for v in phrase_variants("ar", "invite_stop")), spoken
    assert not any(v in spoken for v in phrase_variants("ar", "check")), spoken
    assert "Mona" in spoken, "the student's name should be used when known"
    peak, _ = _stats(audio)
    assert len(audio) > 24000 and peak > AUDIBLE_PEAK


async def test_confirming_advances_and_answering_does_not():
    from app.curriculum import get_topic

    topic = get_topic("binary-search")
    provider = MockRealtimeProvider("gemini")
    await provider.start_session(
        SessionConfig(session_id="s", language="en", system_instruction="",
                      metadata={"topic_title": topic.title, "sections": topic.lesson_plan()})
    )
    await _turns(provider, [""])                       # opening -> step 1

    (answered, _), = await _turns(
        provider, ['The student asked (in English): "why does the range halve?"']
    )
    assert "Good question" in answered
    assert "Trace it on a small array" not in answered, "a question must not skip the step"

    (agreed, _), = await _turns(provider, ["yes, I got it"])
    assert "Exactly" in agreed or "well done" in agreed.lower()
    assert "trace it on a small array" in agreed.lower(), "confirmation should move to step 2"


async def test_saying_you_do_not_understand_rephrases_without_advancing():
    from app.curriculum import get_topic

    topic = get_topic("limits")
    provider = MockRealtimeProvider("gemini")
    await provider.start_session(
        SessionConfig(session_id="s", language="en", system_instruction="",
                      metadata={"topic_title": topic.title, "sections": topic.lesson_plan()})
    )
    await _turns(provider, [""])

    (first_no, _), = await _turns(provider, ["no, I don't understand"])
    assert "another way" in first_no or "simpler" in first_no
    assert any(v in first_no for v in phrase_variants("en", "encourage")), first_no
    assert "One-sided limits" not in first_no, "the tutor must not advance past a confusion"

    (second_no, _), = await _turns(provider, ["still confused"])
    # never the same sentence twice
    assert second_no != first_no
    assert "One-sided limits" not in second_no


async def test_walking_the_whole_plan_reaches_a_closing_line():
    from app.curriculum import get_topic

    topic = get_topic("limits")
    provider = MockRealtimeProvider("gemini")
    await provider.start_session(
        SessionConfig(session_id="s", language="sw", system_instruction="",
                      metadata={"topic_title": topic.title, "sections": topic.lesson_plan()})
    )
    lines = [(await _turns(provider, [""]))[0][0]]
    for _ in range(len(topic.sections) + 1):
        lines.append((await _turns(provider, ["ndiyo, nimeelewa"]))[0][0])

    assert "Limits" in lines[0]
    for step in topic.section_titles[:3]:
        assert any(step.lower() in line.lower() for line in lines), f"step '{step}' was never taught"
    # The walk reached a Swahili closing line (it may be in any of its variants, and
    # the merged turns mean it can arrive earlier than the raw section count).
    assert any(any(v in line for v in phrase_variants("sw", "close")) for line in lines), lines


async def test_language_switch_prompt_is_answered_in_the_new_language():
    from app.curriculum import get_topic
    from app.prompts.interaction import build_language_switch_prompt

    topic = get_topic("mitosis")
    provider = MockRealtimeProvider("gemini")
    await provider.start_session(
        SessionConfig(session_id="s", language="en", system_instruction="",
                      metadata={"topic_title": topic.title, "sections": topic.lesson_plan()})
    )
    await _turns(provider, [""])
    provider.config.language = "ar"                    # the service reconnects in the new language
    provider.dialogue = TutorDialogue.from_metadata(provider.config.metadata, "ar")
    (spoken, _), = await _turns(provider, [build_language_switch_prompt("ar")])
    assert "سنُكمل بالعربية" in spoken
    assert "Interphase first" in spoken, "the lesson continues from the current step"


async def test_llm_mock_converses_for_composed_pipelines():
    """Igbo and Yoruba run composed pipelines; the text component interacts too."""
    from app.curriculum import get_topic

    topic = get_topic("limits")
    metadata = {"topic_id": topic.id, "topic_title": topic.title, "sections": topic.lesson_plan()}
    llm = MockLLMProvider("gemini")

    async def reply(line):
        events = [e async for e in llm.stream_reply(
            [{"role": "user", "content": line}], system_instruction="", language="ig",
            metadata=metadata)]
        return next(e.text for e in events if e.type is ProviderEventType.TURN_COMPLETE)

    opening = await reply("Greet the student and begin.")
    assert opening.startswith("Ndeewo") and "What a limit means" in opening
    # Igbo scaffolding, and the opening hands the turn over instead of quizzing.
    assert any(v in opening for v in phrase_variants("ig", "invite_stop")), opening

    confused = await reply("mba, aghọtaghị m")
    assert any(v in confused for v in phrase_variants("ig", "rephrase")), confused
    assert "One-sided limits" not in confused, "confusion must not advance the plan"

    agreed = await reply("ee, m ghọtara")
    assert "One-sided limits" in agreed


async def test_llm_mock_without_a_plan_keeps_its_reply():
    llm = MockLLMProvider("gemini", reply="LERNA pool answer.")
    events = [e async for e in llm.stream_reply(
        [{"role": "user", "content": "q"}], system_instruction="", language="en", metadata={}
    )]
    assert next(e.text for e in events if e.type is ProviderEventType.TURN_COMPLETE) == "LERNA pool answer."


async def test_explicit_reply_still_overrides_the_plan():
    """Tests (and any caller that passes `reply`) keep getting that exact line."""
    provider = MockRealtimeProvider("gemini", reply="Gemini tutor speaking.")
    await provider.start_session(
        SessionConfig(session_id="s", language="en", system_instruction="",
                      metadata={"topic_title": "Ignored", "sections": [{"title": "x", "goal": "y"}]})
    )
    assert provider.reply_for_turn() == "Gemini tutor speaking."


async def test_tts_component_returns_speakable_audio_in_chunks():
    tts = MockTTSProvider("gemini")
    chunks = [c async for c in tts.synthesize_stream("A short sentence.", "en")]
    assert len(chunks) > 2
    assert sum(len(c.data) for c in chunks) >= 24000 * 0.5 * 2
    peak, _ = _stats(b"".join(c.data for c in chunks))
    assert peak > AUDIBLE_PEAK, f"TTS audio is inaudible (peak {peak})"
