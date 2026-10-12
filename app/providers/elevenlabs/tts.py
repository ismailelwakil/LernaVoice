"""ElevenLabs streaming TTS — BACKUP #1 component (§9).

WSS wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input
Output is requested as raw PCM 24 kHz so it matches the Gemini Live output
format and the client never has to switch decoders mid-session.

Language limitation (verified): the v4 / v4-turbo language list covers Hausa,
Somali, Swahili, Zulu, Amharic, Arabic, French and English but **not Igbo and
not Yoruba** — those two route to Gemini TTS instead.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import contextlib
import json
from typing import Any, AsyncIterator
from urllib.parse import urlencode

from app.config import Settings, get_settings
from app.providers.base import (
    AudioChunk,
    ProviderAuthError,
    ProviderUnsupportedError,
    TextToSpeechProvider,
)
from app.providers.capabilities import Capability, PROVIDER_CAPABILITIES
from app.providers.ws_utils import classify_exception, require_websockets

BASE_WS = "wss://api.elevenlabs.io/v1/text-to-speech"
BASE_REST = "https://api.elevenlabs.io/v1/text-to-speech"

logger = logging.getLogger(__name__)

#: Models that only answer over REST (verified live: v4 rejects the stream-input
#: WebSocket with HTTP 400 whatever the output format, REST returns 200 PCM).
REST_ONLY_MODELS = {"eleven_v4", "eleven_v4_turbo"}

#: Low-latency streaming model and the languages it covers well. Outside this set
#: nothing is streamed: the configured (wider, slower) model is used over REST
#: instead, because a supported voice matters more than a 1.5 s head start.
STREAMING_MODEL = "eleven_multilingual_v2"
STREAMING_LANGUAGES = {
    "en", "ar", "fr", "de", "es", "it", "pt", "pl", "tr", "nl", "sv", "da", "fi",
    "cs", "sk", "ru", "uk", "ro", "hu", "el", "bg", "hr", "id", "ms", "vi", "ja",
    "ko", "zh", "hi", "ta", "fil", "no",
}


class ElevenLabsTTSProvider(TextToSpeechProvider):
    provider_name = "elevenlabs"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._cancelled = False
        self._ws: Any = None
        #: Transport the last line used: "ws" or "rest" (reported by the tools).
        self.last_transport: str | None = None

    async def cancel(self) -> None:
        self._cancelled = True
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()

    async def synthesize_stream(
        self, text: str, language: str, *, voice: str | None = None
    ) -> AsyncIterator[AudioChunk]:
        """Speak `text`: stream over the WebSocket when the model allows it, else REST.

        Both transports deliver identical PCM16 at the session's output rate, so the
        client cannot tell them apart — only the time to first audio differs
        (~300 ms streaming, ~1.5-2 s for a full line over REST).
        """
        if not PROVIDER_CAPABILITIES["elevenlabs"].supports(Capability.TTS, language):
            raise ProviderUnsupportedError(
                f"ElevenLabs TTS does not cover '{language}'", provider="elevenlabs"
            )
        if not self.settings.elevenlabs_api_key:
            raise ProviderAuthError("ELEVENLABS_API_KEY is not configured", provider="elevenlabs")

        self._cancelled = False
        voice_id = voice or self.settings.elevenlabs_voice_id
        model = self.settings.elevenlabs_tts_model
        transport = (getattr(self.settings, "elevenlabs_transport", "auto") or "auto").lower()
        streamable = language in STREAMING_LANGUAGES and STREAMING_MODEL not in REST_ONLY_MODELS
        if transport == "stream":
            wants_stream = streamable
        elif transport == "rest":
            wants_stream = False
        else:  # auto: the socket whenever the language supports it
            wants_stream = streamable
        stream_model = STREAMING_MODEL if model in REST_ONLY_MODELS else model

        if wants_stream:
            self.last_transport = "ws"
            emitted = False
            try:
                async for chunk in self._ws_chunks(text, language, voice_id, stream_model):
                    emitted = True
                    yield chunk
                return
            except Exception as exc:  # noqa: BLE001 - transport problems fall back
                if emitted:
                    raise classify_exception(exc, "elevenlabs") from exc
                logger.warning("ElevenLabs streaming unavailable (%s); using REST", exc)

        self.last_transport = "rest"
        async for chunk in self._rest_chunks(text, language, voice_id, model):
            yield chunk

    async def _ws_chunks(
        self, text: str, language: str, voice_id: str, model: str
    ) -> AsyncIterator[AudioChunk]:
        websockets = require_websockets()
        params = {
            "model_id": model,
            "output_format": f"pcm_{self.settings.output_sample_rate}",
            "inactivity_timeout": 20,
        }
        url = f"{BASE_WS}/{voice_id}/stream-input?{urlencode(params)}"
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    url,
                    additional_headers={"xi-api-key": self.settings.elevenlabs_api_key},
                    max_size=None,
                ),
                timeout=self.settings.voice_provider_timeout,
            )
            await self._ws.send(
                json.dumps(
                    {
                        "text": " ",
                        "voice_settings": {
                            "stability": 0.5,
                            "similarity_boost": 0.8,
                            "speed": float(getattr(self.settings, "elevenlabs_speech_speed", 1.0)),
                        },
                        "generation_config": {"chunk_length_schedule": [120, 160, 250, 290]},
                    }
                )
            )
            await self._ws.send(json.dumps({"text": text, "flush": True}))
            await self._ws.send(json.dumps({"text": ""}))

            async for raw in self._ws:
                if self._cancelled:
                    break
                if isinstance(raw, bytes):
                    yield AudioChunk(data=raw, sample_rate=self.settings.output_sample_rate)
                    continue
                msg = json.loads(raw)
                if msg.get("error"):
                    raise classify_exception(RuntimeError(str(msg)), "elevenlabs")
                audio_b64 = msg.get("audio")
                if audio_b64:
                    yield AudioChunk(
                        data=base64.b64decode(audio_b64), sample_rate=self.settings.output_sample_rate
                    )
                if msg.get("isFinal") or msg.get("is_final"):
                    break
        except Exception as exc:
            raise classify_exception(exc, "elevenlabs") from exc
        finally:
            if self._ws is not None:
                with contextlib.suppress(Exception):
                    await self._ws.close()
                self._ws = None

    async def _rest_chunks(
        self, text: str, language: str, voice_id: str, model: str
    ) -> AsyncIterator[AudioChunk]:
        """One HTTP call, the whole line back as PCM, re-chunked for the socket."""
        import httpx

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.voice_provider_timeout * 3
            ) as client:
                response = await client.post(
                    f"{BASE_REST}/{voice_id}",
                    headers={"xi-api-key": self.settings.elevenlabs_api_key},
                    params={"output_format": f"pcm_{self.settings.output_sample_rate}"},
                    json={
                        "text": text,
                        "model_id": model,
                        "voice_settings": {
                            "stability": 0.5,
                            "similarity_boost": 0.8,
                            "speed": float(getattr(self.settings, "elevenlabs_speech_speed", 1.0)),
                        },
                    },
                )
        except Exception as exc:  # noqa: BLE001
            raise classify_exception(exc, "elevenlabs") from exc

        if response.status_code >= 400:
            detail = response.text[:200]
            if response.status_code in (401, 403):
                raise ProviderAuthError(
                    f"ElevenLabs refused the key ({response.status_code}): {detail}",
                    provider="elevenlabs",
                )
            raise classify_exception(
                RuntimeError(f"HTTP {response.status_code}: {detail}"), "elevenlabs"
            )

        data = response.content
        # ~200 ms per chunk at 24 kHz: the client's scheduler sees the same shape as
        # the streaming transport.
        step = self.settings.output_sample_rate // 5 * 2
        for offset in range(0, len(data), step):
            if self._cancelled:
                return
            yield AudioChunk(
                data=data[offset : offset + step], sample_rate=self.settings.output_sample_rate
            )

