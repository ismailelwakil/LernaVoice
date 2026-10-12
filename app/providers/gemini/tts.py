"""Gemini TTS component (`gemini-3.8-flash-tts`, 130+ languages).

This is the only verified route to **Igbo** and **Yoruba** speech synthesis
across the three configured vendors, so it anchors those two pipelines.
Docs: https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-tts
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from app.config import Settings, get_settings
from app.providers.base import (
    AudioChunk,
    ProviderInternalError,
    ProviderUnsupportedError,
    TextToSpeechProvider,
)
from app.providers.capabilities import Capability, PROVIDER_CAPABILITIES
from app.providers.gemini.client import build_genai_client, classify_gemini_error, genai_types
from app.prompts.languages import language_name

CHUNK_BYTES = 4800  # ~100 ms of 24 kHz mono PCM16


class GeminiTTSProvider(TextToSpeechProvider):
    provider_name = "gemini"

    def __init__(self, settings: Settings | None = None, client: Any | None = None):
        self.settings = settings or get_settings()
        self._client = client
        self._cancelled = False

    async def cancel(self) -> None:
        self._cancelled = True

    async def synthesize_stream(
        self, text: str, language: str, *, voice: str | None = None
    ) -> AsyncIterator[AudioChunk]:
        if not PROVIDER_CAPABILITIES["gemini"].supports(Capability.TTS, language):
            raise ProviderUnsupportedError(f"Gemini TTS does not cover '{language}'", provider="gemini")
        self._cancelled = False
        try:
            types = genai_types()
            if self._client is None:
                self._client = build_genai_client(self.settings)
            prompt = f"Read this aloud naturally in {language_name(language)}:\n{text}"
            response = await self._client.aio.models.generate_content(
                model=self.settings.gemini_tts_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice or self.settings.gemini_voice_name
                            )
                        )
                    ),
                ),
            )
        except Exception as exc:
            raise classify_gemini_error(exc) from exc

        audio = _extract_audio(response)
        if not audio:
            raise ProviderInternalError("Gemini TTS returned no audio", provider="gemini")
        for offset in range(0, len(audio), CHUNK_BYTES):
            if self._cancelled:
                return
            yield AudioChunk(data=audio[offset : offset + CHUNK_BYTES], sample_rate=24000)
            await asyncio.sleep(0)


def _extract_audio(response: Any) -> bytes:
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None)
            if data:
                return data
    return b""
