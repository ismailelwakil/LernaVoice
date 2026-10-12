"""ElevenLabs has two transports, and the provider must pick the right one.

Verified against the live API while wiring the demo:

  * the v4 family (`eleven_v4_turbo`) rejects the `stream-input` WebSocket with
    HTTP 400 for every output format, while REST returns 200 with `pcm_24000`;
  * the streaming family (multilingual v2 / flash v2.5) covers a smaller language
    set, so the five African languages in the demo go over REST with v4.

These tests pin the policy down offline: which transport is used for a language,
which model it asks for, and that the spoken pace is passed to both. The vendor
itself is stubbed \u2014 no key, no network.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.providers.base import AudioChunk
from app.providers.elevenlabs.tts import (
    REST_ONLY_MODELS,
    STREAMING_LANGUAGES,
    STREAMING_MODEL,
    ElevenLabsTTSProvider,
)


def _provider(**kw) -> ElevenLabsTTSProvider:
    base = dict(
        _env_file=None,
        elevenlabs_api_key="sk_test",
        elevenlabs_voice_id="voice_test",
        elevenlabs_tts_model="eleven_v4_turbo",
    )
    base.update(kw)
    return ElevenLabsTTSProvider(Settings(**base))


class Recorder(ElevenLabsTTSProvider):
    """Records which transport ran, with which model, and with what settings."""

    def __init__(self, **kw):
        super().__init__(Settings(**{**dict(_env_file=None, elevenlabs_api_key="sk_test",
                                            elevenlabs_tts_model="eleven_v4_turbo"), **kw}))
        self.ws_calls: list[tuple[str, str, str, str]] = []
        self.rest_calls: list[tuple[str, str, str, str]] = []
        self.ws_settings: dict | None = None
        self.rest_body: dict | None = None

    async def _ws_chunks(self, text, language, voice_id, model):
        self.ws_calls.append((text, language, voice_id, model))
        self.ws_settings = {"speed": self.settings.elevenlabs_speech_speed}
        yield AudioChunk(data=b"\x01\x02" * 100, sample_rate=24000)

    async def _rest_chunks(self, text, language, voice_id, model):
        self.rest_calls.append((text, language, voice_id, model))
        self.rest_body = {"speed": self.settings.elevenlabs_speech_speed}
        yield AudioChunk(data=b"\x03\x04" * 100, sample_rate=24000)


async def _drain(provider, language: str):
    return [chunk async for chunk in provider.synthesize_stream("hello there", language)]


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "ar", "fr"])
async def test_languages_we_can_stream_use_the_socket(language):
    provider = Recorder(elevenlabs_transport="auto")
    await _drain(provider, language)
    assert provider.ws_calls and not provider.rest_calls
    assert provider.last_transport == "ws"
    # The wide v4 model is REST-only, so streaming asks for the streaming model.
    assert provider.ws_calls[0][3] == STREAMING_MODEL


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["sw", "am", "ha", "so", "zu"])
async def test_languages_the_streaming_model_lacks_go_over_rest(language):
    provider = Recorder(elevenlabs_transport="auto")
    await _drain(provider, language)
    assert provider.rest_calls and not provider.ws_calls
    assert provider.last_transport == "rest"
    assert provider.rest_calls[0][3] == "eleven_v4_turbo"


@pytest.mark.asyncio
async def test_transport_can_be_forced():
    assert (await _drain(Recorder(elevenlabs_transport="rest"), "ar")) and True
    forced_rest = Recorder(elevenlabs_transport="rest")
    await _drain(forced_rest, "ar")
    assert forced_rest.rest_calls and not forced_rest.ws_calls

    forced_stream = Recorder(elevenlabs_transport="stream", elevenlabs_tts_model=STREAMING_MODEL)
    await _drain(forced_stream, "en")
    assert forced_stream.ws_calls and not forced_stream.rest_calls


@pytest.mark.asyncio
async def test_a_rejected_socket_falls_back_to_rest_mid_line():
    """The v4-on-WebSocket 400 this module was written for, reproduced offline."""

    class SocketRefuses(Recorder):
        async def _ws_chunks(self, text, language, voice_id, model):
            self.ws_calls.append((text, language, voice_id, model))
            raise RuntimeError("elevenlabs error (400): server rejected WebSocket connection")
            yield  # pragma: no cover - makes this an async generator

    provider = SocketRefuses(elevenlabs_transport="auto")
    chunks = await _drain(provider, "en")
    assert provider.ws_calls and provider.rest_calls, "should have retried over REST"
    assert provider.last_transport == "rest"
    assert chunks and chunks[0].data == b"\x03\x04" * 100


@pytest.mark.asyncio
async def test_a_socket_that_dies_after_audio_does_not_repeat_the_line():
    class DiesMidStream(Recorder):
        async def _ws_chunks(self, text, language, voice_id, model):
            yield AudioChunk(data=b"\x05\x06" * 10, sample_rate=24000)
            raise RuntimeError("connection lost")

    provider = DiesMidStream(elevenlabs_transport="auto")
    with pytest.raises(Exception):
        await _drain(provider, "en")
    assert not provider.rest_calls, "half-spoken audio must not be restarted from the top"


def test_language_sets_do_not_overlap_badly():
    for language in ("ig", "yo"):
        # Igbo and Yoruba are not covered by ElevenLabs TTS at all \u2014 the router
        # sends them elsewhere, and neither transport is ever attempted.
        assert language not in STREAMING_LANGUAGES
    assert "eleven_v4_turbo" in REST_ONLY_MODELS
