"""Round 27 — the voice fails over to a backup (Fish Audio behind Azure)."""

import pytest

from app.providers.base import (
    AudioChunk,
    ProviderAuthError,
    ProviderEventType,
    TextToSpeechProvider,
)
from app.providers.cascade import CascadePipelineProvider
from app.providers.mock.providers import MockLLMProvider, MockSTTProvider


class _DownTTS(TextToSpeechProvider):
    provider_name = "azure"

    async def synthesize_stream(self, text, language, *, voice=None):
        raise ProviderAuthError("azure is down", provider="azure")
        yield  # pragma: no cover


class _PartialTTS(TextToSpeechProvider):
    provider_name = "azure"

    async def synthesize_stream(self, text, language, *, voice=None):
        yield AudioChunk(data=b"\x01\x02" * 50, sample_rate=24000)
        raise ProviderAuthError("dropped mid-line", provider="azure")


class _GoodTTS(TextToSpeechProvider):
    provider_name = "fish"

    async def synthesize_stream(self, text, language, *, voice=None):
        yield AudioChunk(data=b"\x03\x04" * 50, sample_rate=24000)


def _cascade(tts, fallbacks):
    return CascadePipelineProvider(
        stt=MockSTTProvider("deepgram"), llm=MockLLMProvider("openrouter"),
        tts=tts, tts_fallbacks=fallbacks,
    )


@pytest.mark.asyncio
async def test_voice_fails_over_to_backup_before_speaking():
    cascade = _cascade(_DownTTS(), [_GoodTTS()])
    await cascade._speak("أهلًا", "ar")
    ev = cascade._out.get_nowait()
    assert ev.type is ProviderEventType.AUDIO       # the backup (Fish) spoke
    assert ev.audio == b"\x03\x04" * 50


@pytest.mark.asyncio
async def test_all_voices_down_emits_error():
    cascade = _cascade(_DownTTS(), [_DownTTS()])
    await cascade._speak("أهلًا", "ar")
    ev = cascade._out.get_nowait()
    assert ev.type is ProviderEventType.ERROR       # nothing could speak


@pytest.mark.asyncio
async def test_mid_line_failure_is_not_restarted():
    # Azure spoke part of the line, then dropped: surface an error rather than
    # letting the backup repeat what the student already heard.
    cascade = _cascade(_PartialTTS(), [_GoodTTS()])
    await cascade._speak("أهلًا", "ar")
    first = cascade._out.get_nowait()
    assert first.type is ProviderEventType.AUDIO    # the partial audio from Azure
    second = cascade._out.get_nowait()
    assert second.type is ProviderEventType.ERROR   # and an error, not a duplicate


def test_factory_failover_order_azure_gemini_elevenlabs():
    from app.config import Settings
    from app.providers.factory import ProviderFactory

    s = Settings(voice_enable_mock_providers=True)
    factory = ProviderFactory(s)
    factory.register_vendor_mocks()
    azure = factory.build_tts("azure")
    order = [getattr(p, "provider_name", None) for p in factory._tts_failover(azure)]
    assert "azure" not in order                     # never falls back to itself
    # Round 30: Gemini is the second voice, ElevenLabs the third.
    assert order[:2] == ["gemini", "elevenlabs"]
