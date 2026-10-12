"""Deepgram Aura streaming TTS — BACKUP #2 component (§10).

WSS wss://api.deepgram.com/v1/speak, binary linear16 frames out.
Aura-2 covers en, es, de, fr, nl, it, ja only, so within LERNA it can serve
English and French and nothing else. Never used as a general fallback.
"""

from __future__ import annotations

import asyncio
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

BASE_WS = "wss://api.deepgram.com/v1/speak"

VOICE_BY_LANGUAGE = {"en": "aura-2-thalia-en", "fr": "aura-2-pandora-fr"}


class DeepgramTTSProvider(TextToSpeechProvider):
    provider_name = "deepgram"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._cancelled = False
        self._ws: Any = None

    async def cancel(self) -> None:
        self._cancelled = True
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.send(json.dumps({"type": "Clear"}))
                await self._ws.close()

    async def synthesize_stream(
        self, text: str, language: str, *, voice: str | None = None
    ) -> AsyncIterator[AudioChunk]:
        if not PROVIDER_CAPABILITIES["deepgram"].supports(Capability.TTS, language):
            raise ProviderUnsupportedError(f"Deepgram TTS does not cover '{language}'", provider="deepgram")
        if not self.settings.deepgram_api_key:
            raise ProviderAuthError("DEEPGRAM_API_KEY is not configured", provider="deepgram")

        self._cancelled = False
        websockets = require_websockets()
        params = {
            "model": voice or VOICE_BY_LANGUAGE.get(language, self.settings.deepgram_tts_model),
            "encoding": "linear16",
            "sample_rate": self.settings.output_sample_rate,
        }
        url = f"{BASE_WS}?{urlencode(params)}"
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    url,
                    additional_headers={"Authorization": f"Token {self.settings.deepgram_api_key}"},
                    max_size=None,
                ),
                timeout=self.settings.voice_provider_timeout,
            )
            await self._ws.send(json.dumps({"type": "Speak", "text": text}))
            await self._ws.send(json.dumps({"type": "Flush"}))

            async for raw in self._ws:
                if self._cancelled:
                    break
                if isinstance(raw, bytes):
                    yield AudioChunk(data=raw, sample_rate=self.settings.output_sample_rate)
                    continue
                msg = json.loads(raw)
                if msg.get("type") in ("Flushed", "Close"):
                    break
                if msg.get("type") == "Error":
                    raise classify_exception(RuntimeError(str(msg)[:300]), "deepgram")
        except Exception as exc:
            raise classify_exception(exc, "deepgram") from exc
        finally:
            if self._ws is not None:
                with contextlib.suppress(Exception):
                    await self._ws.close()
                self._ws = None
