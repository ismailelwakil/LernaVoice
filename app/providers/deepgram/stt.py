"""Deepgram streaming STT — BACKUP #2 component (§10).

WSS wss://api.deepgram.com/v1/listen with `Authorization: Token <key>`.
Binary frames carry linear16 PCM; JSON `Results` messages carry transcripts and
`is_final` / `speech_final` turn boundaries.

Verified language limitation: of LERNA's ten languages Deepgram's published
Nova-3 list covers only en, ar and fr. Deepgram is therefore a *component*,
never a complete voice stack.
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
    ProviderEvent,
    ProviderEventType,
    ProviderInternalError,
    ProviderUnsupportedError,
    SpeechToTextProvider,
)
from app.providers.capabilities import Capability, PROVIDER_CAPABILITIES
from app.providers.ws_utils import classify_exception, require_websockets

BASE_WS = "wss://api.deepgram.com/v1/listen"


class DeepgramSTTProvider(SpeechToTextProvider):
    provider_name = "deepgram"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._ws: Any = None
        self._queue: asyncio.Queue[ProviderEvent | None] = asyncio.Queue()
        self._reader: asyncio.Task | None = None

    async def start_stream(self, language: str, sample_rate: int = 16000) -> None:
        if not PROVIDER_CAPABILITIES["deepgram"].supports(Capability.STT, language):
            raise ProviderUnsupportedError(f"Deepgram STT does not cover '{language}'", provider="deepgram")
        if not self.settings.deepgram_api_key:
            raise ProviderAuthError("DEEPGRAM_API_KEY is not configured", provider="deepgram")
        websockets = require_websockets()
        params = {
            "model": self.settings.deepgram_stt_model,
            "language": language,
            "encoding": "linear16",
            "sample_rate": sample_rate,
            "channels": 1,
            "interim_results": "true",
            "punctuate": "true",
            "smart_format": "true",
            "endpointing": 300,
            "vad_events": "true",
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
        except Exception as exc:
            raise classify_exception(exc, "deepgram") from exc
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    continue
                msg = json.loads(raw)
                kind = msg.get("type")
                if kind == "Results":
                    alt = (msg.get("channel", {}).get("alternatives") or [{}])[0]
                    text = alt.get("transcript", "")
                    if not text:
                        continue
                    await self._queue.put(
                        ProviderEvent(
                            type=ProviderEventType.INPUT_TRANSCRIPT,
                            text=text,
                            partial=not msg.get("is_final", False),
                        )
                    )
                elif kind == "SpeechStarted":
                    await self._queue.put(ProviderEvent(type=ProviderEventType.SPEECH_STARTED))
                elif kind == "UtteranceEnd":
                    await self._queue.put(ProviderEvent(type=ProviderEventType.SPEECH_STOPPED))
                elif kind == "Error":
                    await self._queue.put(
                        ProviderEvent(
                            type=ProviderEventType.ERROR,
                            error=ProviderInternalError(str(msg)[:300], provider="deepgram"),
                        )
                    )
        except Exception as exc:
            await self._queue.put(
                ProviderEvent(type=ProviderEventType.ERROR, error=classify_exception(exc, "deepgram"))
            )
        finally:
            await self._queue.put(None)

    async def send_audio(self, chunk: AudioChunk) -> None:
        if self._ws is None:
            raise ProviderInternalError("Deepgram STT stream is not open", provider="deepgram")
        try:
            await self._ws.send(chunk.data)
        except Exception as exc:
            raise classify_exception(exc, "deepgram") from exc

    async def finalize(self) -> None:
        if self._ws is None:
            return
        with contextlib.suppress(Exception):
            await self._ws.send(json.dumps({"type": "Finalize"}))

    async def receive_events(self) -> AsyncIterator[ProviderEvent]:
        while True:
            event = await self._queue.get()
            if event is None:
                return
            yield event

    async def stop_stream(self) -> None:
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.send(json.dumps({"type": "CloseStream"}))
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        if self._reader:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader
            self._reader = None
        await self._queue.put(None)
