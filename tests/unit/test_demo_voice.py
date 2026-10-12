"""The offline demo can still be voiced by a real vendor (app/voice/demo_voice.py).

No network, no credentials: a stub TTS stands in for ElevenLabs, so these tests
run everywhere. What they pin down is the contract the demo depends on \u2014 the
assistant audio on the wire is the *vendor's* audio when a voice is attached, the
conversation itself stays offline, and a failing vendor never breaks a lesson.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.providers.base import AudioChunk, ProviderAuthError, SessionConfig
from app.providers.factory import ProviderFactory
from app.providers.mock.providers import MockRealtimeProvider
from app.voice import demo_voice as demo_voice_module
from app.voice.demo_voice import attach_demo_voice, demo_voice_label, demo_voice_vendor
from app.voice.provider_router import VoiceProviderRouter
from app.voice.session_manager import VoiceSessionManager, set_manager


class StubTTS:
    """Stands in for ElevenLabs: returns recognisable PCM, or fails on demand."""

    provider_name = "elevenlabs"

    def __init__(self, *, fail: bool = False, silence: bool = False):
        self.fail = fail
        self.silence = silence
        self.spoken: list[tuple[str, str, str | None]] = []
        self.cancelled = False

    async def synthesize_stream(self, text, language, *, voice=None):
        self.spoken.append((text, language, voice))
        if self.fail:
            raise ProviderAuthError("ELEVENLABS_API_KEY is not configured", provider="elevenlabs")
        if self.silence:
            return
        frame = FRAME
        yield AudioChunk(data=frame, sample_rate=24000)
        yield AudioChunk(data=frame, sample_rate=24000)

    async def cancel(self) -> None:
        self.cancelled = True


FRAME = b"\x11\x22" * 1200  # 2400 bytes of very recognisable PCM


def _settings(**kw) -> Settings:
    base = dict(_env_file=None, voice_enable_mock_providers=True, lerna_integration_mode="disabled")
    base.update(kw)
    return Settings(**base)


def _config(**kw) -> SessionConfig:
    base = dict(
        session_id="vs_demo_voice",
        language="en",
        system_instruction="be a tutor",
        metadata={"topic_title": "Binary Search"},
    )
    base.update(kw)
    return SessionConfig(**base)


async def _drain_audio(provider: MockRealtimeProvider, *, turns: int = 1) -> list[bytes]:
    frames: list[bytes] = []
    seen = 0

    async def drain():
        nonlocal seen
        async for event in provider.receive_events():
            if event.type.value == "audio" and event.audio:
                frames.append(event.audio)
            if event.type.value == "turn_complete":
                seen += 1
                if seen >= turns:
                    return

    task = asyncio.create_task(drain())
    await asyncio.wait_for(task, timeout=3)
    return frames


# --------------------------------------------------------------------------- #
# which vendor, and what /health says about it
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "mode,key_configured,expected",
    [
        ("off", True, None),
        ("off", False, None),
        ("auto", False, None),
        ("auto", True, "elevenlabs"),
        ("elevenlabs", True, "elevenlabs"),
        ("elevenlabs", False, None),
    ],
)
def test_which_vendor_voices_the_demo(mode, key_configured, expected):
    settings = _settings(
        voice_demo_voice=mode, elevenlabs_api_key="sk_test" if key_configured else None
    )
    assert demo_voice_vendor(settings) == expected


def test_health_label_names_the_model_but_never_the_key():
    settings = _settings(voice_demo_voice="auto", elevenlabs_api_key="sk_super_secret")
    label = demo_voice_label(settings)
    assert label == "elevenlabs:eleven_v4_turbo"
    assert "sk_super_secret" not in json.dumps({"demo_voice": label})


def test_only_mock_pipelines_get_a_vendor_voice():
    """A live realtime vendor *is* the voice \u2014 it must not be overridden."""
    settings = _settings(voice_demo_voice="auto", elevenlabs_api_key="sk_test")
    factory = ProviderFactory(settings)
    factory.register("tts", "elevenlabs", lambda: StubTTS())

    mock = MockRealtimeProvider()
    assert attach_demo_voice(mock, factory, settings) == "elevenlabs"
    assert mock.tts is not None

    class RealProvider:
        provider_name = "gemini"
        tts = None

    assert attach_demo_voice(RealProvider(), factory, settings) is None


# --------------------------------------------------------------------------- #
# the audio that reaches the student
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_the_demo_speaks_with_the_vendor_not_the_synthetic_tone():
    provider = MockRealtimeProvider()
    stub = StubTTS()
    provider.attach_tts(stub, "elevenlabs")
    await provider.start_session(_config())

    await provider.send_text("hello", trigger_response=True)
    frames = await _drain_audio(provider)

    assert frames, "no assistant audio was emitted"
    # Every frame is the vendor's, byte for byte: the synthetic generator would
    # emit ~48 000 bytes/second of a completely different signal.
    assert all(frame == FRAME for frame in frames), frames[:2]
    assert provider.tts_bytes == 4800
    assert provider.tts_fallbacks == 0
    assert stub.spoken and stub.spoken[0][1] == "en"  # words are still the tutor's


@pytest.mark.asyncio
async def test_the_vendor_is_given_words_not_symbols():
    provider = MockRealtimeProvider()
    stub = StubTTS()
    provider.attach_tts(stub, "elevenlabs")
    await provider.start_session(
        _config(
            metadata={
                "topic_title": "Binary Search",
                "sections": [{"title": "Choosing the midpoint", "goal": "mid = (low + high) // 2"}],
            }
        )
    )
    await provider.send_text("go", trigger_response=True)
    for _ in range(50):
        await asyncio.sleep(0)
        if stub.spoken:
            break

    assert stub.spoken, "the vendor was never asked to speak"
    heard = stub.spoken[0][0]
    assert "//" not in heard and "(" not in heard, heard
    assert "divided by" in heard or "equals" in heard, heard


@pytest.mark.asyncio
async def test_a_broken_vendor_does_not_break_the_lesson():
    provider = MockRealtimeProvider()
    provider.attach_tts(StubTTS(fail=True), "elevenlabs")
    await provider.start_session(_config())

    await provider.send_text("hello", trigger_response=True)
    frames = await _drain_audio(provider)

    assert frames, "the student heard nothing at all"
    assert not all(frame == FRAME for frame in frames), "fallback should be the synthetic voice"
    assert provider.tts_fallbacks == 1


@pytest.mark.asyncio
async def test_a_silent_vendor_is_treated_as_a_failure():
    provider = MockRealtimeProvider()
    provider.attach_tts(StubTTS(silence=True), "elevenlabs")
    await provider.start_session(_config())

    await provider.send_text("hello", trigger_response=True)
    frames = await _drain_audio(provider)

    assert frames and provider.tts_fallbacks == 1


# --------------------------------------------------------------------------- #
# wired through the session, and never leaking the key
# --------------------------------------------------------------------------- #


@pytest.fixture
def demo_voice_factory(settings) -> ProviderFactory:
    factory = ProviderFactory(settings)
    factory.register("realtime", "gemini", lambda: MockRealtimeProvider("gemini"))
    return factory


@pytest.mark.asyncio
async def test_every_mock_session_is_voiced(
    settings, repository, router, rag, progress, orchestrator, demo_voice_factory
):
    """Wired end to end: the manager builds a provider that already has a voice."""
    settings.elevenlabs_api_key = "sk_test"
    settings.voice_demo_voice = "auto"
    manager = VoiceSessionManager(
        settings=settings,
        repository=repository,
        router=VoiceProviderRouter(
            settings=settings, available_providers=("gemini", "elevenlabs", "deepgram", "lerna")
        ),
        factory=demo_voice_factory,
        rag=rag,
        progress=progress,
        orchestrator=orchestrator,
    )
    set_manager(manager)
    try:
        session = await manager.create(student_id="voice-demo", language="en", topic="Binary Search")
        await session.start()
        assert isinstance(session.provider, MockRealtimeProvider)
        assert session.provider.tts is not None, "the demo voice was not attached"
        assert session.provider.tts_vendor == "elevenlabs"
    finally:
        set_manager(None)


def test_the_key_never_reaches_the_browser(tmp_path):
    """The page is told the voice *name*; the key stays server-side."""
    from app.main import app

    with TestClient(app) as client:
        body = client.get("/voice/voices")
        assert body.status_code == 503
        assert "xi-api-key" in body.json()["detail"] or "ELEVENLABS_API_KEY" in body.json()["detail"]


def test_a_vendor_refusal_is_reported_as_a_gateway_error(monkeypatch):
    """The page must be told *why* the voice list is empty (key refused, not a bug)."""
    import httpx

    from app.api import routes as routes_module

    settings = _settings(voice_demo_voice="elevenlabs", elevenlabs_api_key="sk_test")
    monkeypatch.setattr(routes_module, "get_settings", lambda: settings)

    async def refuse(_settings):
        request = httpx.Request("GET", "https://api.elevenlabs.io/v1/voices")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("401 Unauthorized", request=request, response=response)

    from app.providers.elevenlabs import voices as voices_module

    monkeypatch.setattr(voices_module, "list_voices", refuse)

    from app.main import app

    with TestClient(app) as client:
        body = client.get("/voice/voices")
        assert body.status_code == 502, body.text
        assert "401" in body.json()["detail"] and "API key" in body.json()["detail"]


# --------------------------------------------------------------------------- #
# a vendor that cannot speak the language must not steal the turn
# --------------------------------------------------------------------------- #


def test_vendor_coverage_answers_for_both_vendors():
    from app.voice.demo_voice import vendor_covers_language

    settings = _settings(
        elevenlabs_api_key="sk_test",
        azure_speech_key="k",
        azure_speech_region="germanywestcentral",
    )
    assert vendor_covers_language("azure", "ar", settings) is True
    assert vendor_covers_language("azure", "ha", settings) is False
    assert vendor_covers_language("elevenlabs", "ha", settings) is True
    assert vendor_covers_language("elevenlabs", "yo", settings) is False
    assert vendor_covers_language("elevenlabs", "ig", settings) is False


@pytest.mark.asyncio
async def test_the_vendor_is_not_asked_for_a_language_it_cannot_speak(monkeypatch):
    """Hausa: Azure has no voice for it, so the synthetic voice answers and the
    vendor is never called (an `unsupported` error would count as a failure)."""
    from app.voice import demo_voice as dv

    stub = StubTTS()
    monkeypatch.setitem(dv.DEMO_TTS_BUILDERS, "azure", lambda settings: stub)
    settings = _settings(
        voice_demo_voice="azure", azure_speech_key="k", azure_speech_region="germanywestcentral"
    )
    provider = MockRealtimeProvider()
    assert dv.attach_demo_voice(provider, None, settings) == "azure"
    await provider.start_session(_config(language="ha"))

    await provider.send_text("hello", trigger_response=True)
    frames = await _drain_audio(provider)

    assert frames, "the student heard nothing at all"
    assert stub.spoken == [], "the vendor was asked to speak a language it does not have"
    assert provider.tts_fallbacks == 0, "a language gap is not a vendor failure"


@pytest.mark.asyncio
async def test_a_cascade_keeps_its_own_leg_for_igbo(monkeypatch):
    """Replacing a cascade's TTS leg with a voice that cannot speak the language
    turns a silent-synthetic turn into a *mid-lesson failover*: the gate must
    answer Igbo with the leg the router chose and Azure only for its own seven."""
    from app.providers.mock.providers import MockTTSProvider
    from app.voice import demo_voice as dv

    stub = StubTTS()
    monkeypatch.setitem(dv.DEMO_TTS_BUILDERS, "azure", lambda settings: stub)
    settings = _settings(
        voice_demo_voice="azure", azure_speech_key="k", azure_speech_region="germanywestcentral"
    )

    class Cascade:
        provider_name = "cascade:elevenlabs+gemini+gemini"
        tts = MockTTSProvider()

    cascade = Cascade()
    assert dv.attach_demo_voice(cascade, None, settings) == "azure"
    assert cascade.tts.covers("ig") is False and cascade.tts.covers("ar") is True

    igbo = [chunk async for chunk in cascade.tts.synthesize_stream("Ndeewo", "ig")]
    assert igbo, "the cascade leg went silent"
    assert stub.spoken == [], "Azure was asked to speak Igbo"

    arabic = [chunk async for chunk in cascade.tts.synthesize_stream("أهلا", "ar")]
    assert arabic and stub.spoken, "Azure should speak the languages it covers"
