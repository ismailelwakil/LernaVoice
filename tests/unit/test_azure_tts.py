"""Azure AI Speech TTS \u2014 the official free-tier voice (F0: 0.5M characters/month).

Offline: `httpx` is stubbed, so the tests pin the request Azure would receive (SSML
voice, output format, key header) and the PCM the client would hear \u2014 no key, no
network, no characters spent.
"""

from __future__ import annotations

import struct

import httpx
import pytest

from app.config import Settings
from app.providers.azure.tts import AzureTTSProvider, voice_for
from app.providers.base import ProviderAuthError, ProviderUnsupportedError

WAV_HEADER = b"".join(
    [
        b"RIFF",
        struct.pack("<I", 36 + 4800),
        b"WAVE",
        b"fmt ",
        struct.pack("<IHHIIHH", 16, 1, 1, 24000, 48000, 2, 16),
        b"data",
        struct.pack("<I", 4800),
    ]
)
FRAMES = struct.pack("<600h", *range(-300, 300))
WAV = WAV_HEADER + FRAMES


def _settings(**kw) -> Settings:
    base = dict(
        _env_file=None,
        azure_speech_key="azure_test_key",
        azure_speech_region="eastus",
        output_sample_rate=24000,
    )
    base.update(kw)
    return Settings(**base)


class Recorder:
    """Captures the request the provider would send to Azure."""

    def __init__(self, response: httpx.Response):
        self.response = response
        self.request: httpx.Request | None = None

    def install(self, monkeypatch, provider: AzureTTSProvider) -> None:
        recorder = self

        class _Client:
            def __init__(self, *_, **__):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, headers=None, content=None, params=None, json=None):
                recorder.request = httpx.Request("POST", url, headers=headers, content=content)
                return recorder.response

        monkeypatch.setattr(httpx, "AsyncClient", _Client)


async def _speak(provider, text="أهلاً بك", language="ar"):
    chunks = [chunk async for chunk in provider.synthesize_stream(text, language)]
    return b"".join(chunk.data for chunk in chunks)


@pytest.mark.asyncio
async def test_requests_the_arabic_voice_as_raw_pcm(monkeypatch):
    recorder = Recorder(httpx.Response(200, content=WAV))
    provider = AzureTTSProvider(_settings())
    recorder.install(monkeypatch, provider)

    pcm = await _speak(provider)

    request = recorder.request
    assert request.url.host == "eastus.tts.speech.microsoft.com"
    assert request.headers["Ocp-Apim-Subscription-Key"] == "azure_test_key"
    assert request.headers["X-Microsoft-OutputFormat"] == "riff-24khz-16bit-mono-pcm"
    body = request.content.decode()
    assert "ar-SA-ZariyahNeural" in body and "أهلاً بك" in body
    # The WAV container is stripped: the client gets bare PCM16 it can schedule.
    assert pcm == FRAMES


@pytest.mark.asyncio
async def test_every_covered_language_has_a_voice_and_the_outside_ones_are_refused(monkeypatch):
    recorder = Recorder(httpx.Response(200, content=WAV))
    recorder.install(monkeypatch, AzureTTSProvider(_settings()))
    for language in ("en", "ar", "fr", "sw", "am", "so", "zu"):
        provider = AzureTTSProvider(_settings())
        await _speak(provider, "hello", language)
        assert recorder.request is not None
        assert "xml:lang" in recorder.request.content.decode()

    for language in ("ig", "yo", "ha"):
        with pytest.raises(ProviderUnsupportedError):
            await _speak(AzureTTSProvider(_settings()), "sannu", language)


@pytest.mark.asyncio
async def test_speed_is_passed_as_prosody(monkeypatch):
    recorder = Recorder(httpx.Response(200, content=WAV))
    recorder.install(monkeypatch, AzureTTSProvider(_settings(azure_speech_speed=1.15)))
    await _speak(AzureTTSProvider(_settings(azure_speech_speed=1.15)))
    assert 'rate="+15%"' in recorder.request.content.decode()


@pytest.mark.asyncio
async def test_a_refused_key_is_an_auth_error_not_a_mystery(monkeypatch):
    recorder = Recorder(httpx.Response(401, content=b'{"error": "invalid key"}'))
    provider = AzureTTSProvider(_settings())
    recorder.install(monkeypatch, provider)
    with pytest.raises(ProviderAuthError):
        await _speak(provider)


@pytest.mark.asyncio
async def test_without_the_key_it_says_so(monkeypatch):
    provider = AzureTTSProvider(Settings(_env_file=None))
    with pytest.raises(ProviderAuthError):
        await _speak(provider)


def test_voices_are_configurable_per_language():
    settings = _settings(azure_voice_overrides="ar:ar-SA-HamedNeural, zu:zu-ZA-ThembaNeural")
    assert voice_for("ar", settings) == "ar-SA-HamedNeural"
    assert voice_for("zu", settings) == "zu-ZA-ThembaNeural"
    assert voice_for("ar", _settings()) == "ar-SA-ZariyahNeural"
    assert voice_for("yo", _settings()) is None


def test_azure_is_the_preferred_demo_voice_when_configured():
    """0.5M characters/month beats 10 000 credits, so `auto` picks Azure."""
    from app.voice.demo_voice import demo_voice_vendor

    both = _settings(elevenlabs_api_key="sk_test")
    assert demo_voice_vendor(both) == "azure"
    only_el = Settings(_env_file=None, elevenlabs_api_key="sk_test")
    assert demo_voice_vendor(only_el) == "elevenlabs"
    assert demo_voice_vendor(_settings(voice_demo_voice="elevenlabs", elevenlabs_api_key="sk")) == "elevenlabs"
    assert demo_voice_vendor(_settings(voice_demo_voice="off")) is None
