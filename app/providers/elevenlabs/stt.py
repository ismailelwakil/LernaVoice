"""ElevenLabs Scribe v2 Realtime streaming STT — BACKUP #1 component (§9).

WSS  wss://api.elevenlabs.io/v1/speech-to-text/realtime
Auth `xi-api-key` header (server side) or a single-use `token` query parameter
     for browser clients — the permanent key never reaches a browser (§40).
Send `{"message_type":"input_audio_chunk","audio_base_64":...,"commit":bool}`
Recv `session_started | partial_transcript | committed_transcript | error`

This is the only verified streaming STT among the three vendors that covers
Igbo, Yoruba and Zulu, so it anchors those pipelines.
Docs: https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from typing import Any, AsyncIterator
from urllib.parse import urlencode

from app.config import Settings, get_settings
from app.logging_setup import get_logger
from app.providers.base import (
    AudioChunk,
    ProviderAuthError,
    ProviderEvent,
    ProviderEventType,
    ProviderInternalError,
    ProviderUnsupportedError,
    SpeechToTextProvider,
)
from app.providers.capabilities import Capability, PROVIDER_CAPABILITIES
from app.providers.ws_utils import classify_exception, require_websockets

log = get_logger(__name__)

BASE_WS = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
BASE_HTTP = "https://api.elevenlabs.io/v1"

# ISO-639-1 -> the ISO-639-3 code ElevenLabs prefers for these languages.
LANGUAGE_CODES = {
    "en": "eng",
    "ar": "ara",
    "fr": "fra",
    "sw": "swa",
    "am": "amh",
    "ha": "hau",
    "so": "som",
    "yo": "yor",
    "ig": "ibo",
    "zu": "zul",
}


class ElevenLabsSTTProvider(SpeechToTextProvider):
    provider_name = "elevenlabs"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._ws: Any = None
        self._queue: asyncio.Queue[ProviderEvent | None] = asyncio.Queue()
        self._reader: asyncio.Task | None = None
        self._language = "en"

    async def start_stream(self, language: str, sample_rate: int = 16000) -> None:
        if not PROVIDER_CAPABILITIES["elevenlabs"].supports(Capability.STT, language):
            raise ProviderUnsupportedError(f"ElevenLabs STT does not cover '{language}'", provider="elevenlabs")
        if not self.settings.elevenlabs_api_key:
            raise ProviderAuthError("ELEVENLABS_API_KEY is not configured", provider="elevenlabs")
        self._language = language
        websockets = require_websockets()
        params = {
            "model_id": self.settings.elevenlabs_stt_model,
            "audio_format": f"pcm_{sample_rate}",
            "language_code": LANGUAGE_CODES.get(language, language),
            "commit_strategy": "vad",
        }
        url = f"{BASE_WS}?{urlencode(params)}"
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    url,
                    additional_headers={"xi-api-key": self.settings.elevenlabs_api_key},
                    max_size=None,
                ),
                timeout=self.settings.voice_provider_timeout,
            )
        except Exception as exc:
            raise classify_exception(exc, "elevenlabs") from exc
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                kind = msg.get("message_type") or msg.get("type")
                if kind in ("partial_transcript", "partial"):
                    await self._queue.put(
                        ProviderEvent(
                            type=ProviderEventType.INPUT_TRANSCRIPT, text=msg.get("text", ""), partial=True
                        )
                    )
                elif kind in ("committed_transcript", "committed", "committed_transcript_with_timestamps"):
                    await self._queue.put(
                        ProviderEvent(
                            type=ProviderEventType.INPUT_TRANSCRIPT, text=msg.get("text", ""), partial=False
                        )
                    )
                elif kind == "session_started":
                    await self._queue.put(ProviderEvent(type=ProviderEventType.CONNECTED, raw=msg))
                elif kind == "error":
                    await self._queue.put(
                        ProviderEvent(
                            type=ProviderEventType.ERROR,
                            error=ProviderInternalError(str(msg.get("error") or msg), provider="elevenlabs"),
                        )
                    )
                elif kind == "warning":
                    log.warning("elevenlabs stt warning", extra={"warning": str(msg.get("warning"))[:200]})
        except Exception as exc:
            await self._queue.put(
                ProviderEvent(type=ProviderEventType.ERROR, error=classify_exception(exc, "elevenlabs"))
            )
        finally:
            await self._queue.put(None)

    async def send_audio(self, chunk: AudioChunk) -> None:
        if self._ws is None:
            raise ProviderInternalError("ElevenLabs STT stream is not open", provider="elevenlabs")
        payload = {
            "message_type": "input_audio_chunk",
            "audio_base_64": base64.b64encode(chunk.data).decode("ascii"),
        }
        try:
            await self._ws.send(json.dumps(payload))
        except Exception as exc:
            raise classify_exception(exc, "elevenlabs") from exc

    async def finalize(self) -> None:
        if self._ws is None:
            return
        with contextlib.suppress(Exception):
            await self._ws.send(json.dumps({"message_type": "input_audio_chunk", "audio_base_64": "", "commit": True}))

    async def receive_events(self) -> AsyncIterator[ProviderEvent]:
        while True:
            event = await self._queue.get()
            if event is None:
                return
            yield event

    async def stop_stream(self) -> None:
        if self._reader:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader
            self._reader = None
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        await self._queue.put(None)

    # ------------------------------------------------------------ ephemeral

    async def create_single_use_token(self) -> str:
        """Short-lived browser token so the permanent key stays server-side (§40)."""
        import httpx

        if not self.settings.elevenlabs_api_key:
            raise ProviderAuthError("ELEVENLABS_API_KEY is not configured", provider="elevenlabs")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{BASE_HTTP}/tokens/single-use",
                headers={"xi-api-key": self.settings.elevenlabs_api_key},
                json={"purpose": "realtime_scribe"},
            )
            if response.status_code >= 400:
                raise classify_exception(
                    ProviderInternalError(response.text[:200], provider="elevenlabs"), "elevenlabs"
                )
            return response.json().get("token", "")
