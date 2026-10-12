"""Gemini Live API realtime voice provider — PRIMARY (§8).

Native audio in / audio out over a stateful WebSocket, with server-side VAD,
barge-in, input+output transcription and function calling.

Docs: https://ai.google.dev/gemini-api/docs/live-api/capabilities
Audio contract: input 16-bit PCM 16 kHz little-endian, output 24 kHz.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, AsyncIterator

from app.config import Settings, get_settings
from app.logging_setup import get_logger

#: Setup fields a model may reject. Only *these* failures are retried without the
#: optional humanising options — a network error must fail over immediately.
_SETUP_REJECTION_HINTS = ("invalid", "unknown field", "unexpected", "validation", "unsupported")
from app.providers.base import (
    AudioChunk,
    ProviderEvent,
    ProviderEventType,
    ProviderInternalError,
    ProviderUnsupportedError,
    RealtimeVoiceProvider,
    SessionConfig,
    ToolHandler,
)
from app.providers.capabilities import Capability, PROVIDER_CAPABILITIES
from app.providers.gemini.client import build_genai_client, classify_gemini_error, genai_types

log = get_logger(__name__)


class GeminiLiveProvider(RealtimeVoiceProvider):
    provider_name = "gemini"
    supports_native_interruption = True
    supports_turn_detection = True

    def __init__(self, settings: Settings | None = None, client: Any | None = None):
        self.settings = settings or get_settings()
        self._client = client
        self._session: Any = None
        self._cm: Any = None
        self._tool_handler: ToolHandler | None = None
        self._closed = asyncio.Event()
        self._model: str = self.settings.active_gemini_live_model

    # ------------------------------------------------------------- lifecycle

    async def start_session(self, config: SessionConfig) -> None:
        cap = PROVIDER_CAPABILITIES["gemini"]
        if not cap.supports(Capability.REALTIME, config.language):
            raise ProviderUnsupportedError(
                f"Gemini Live API does not support realtime conversation in '{config.language}'",
                provider="gemini",
            )
        try:
            types = genai_types()
            if self._client is None:
                self._client = build_genai_client(self.settings)

            live_config: dict[str, Any] = {
                "response_modalities": ["AUDIO"],
                "system_instruction": config.system_instruction,
                "input_audio_transcription": {},
                "output_audio_transcription": {},
            }
            voice = config.voice_name or self.settings.gemini_voice_name
            if voice:
                live_config["speech_config"] = types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                    )
                )
            if config.tools:
                live_config["tools"] = [{"function_declarations": config.tools}]

            # Humanising options on top of the base setup. They are attempted first and
            # dropped if the model/auth path rejects them, so an older live model still
            # connects instead of failing the whole session over a nicety.
            extras: dict[str, Any] = {}
            if self.settings.gemini_affective_dialog:
                extras["enable_affective_dialog"] = True
            if self.settings.gemini_proactive_audio:
                extras["proactivity"] = {"proactive_audio": True}

            attempts = ([{**live_config, **extras}, live_config] if extras else [live_config])
            last: Exception | None = None
            for candidate in attempts:
                try:
                    self._cm = self._client.aio.live.connect(model=self._model, config=candidate)
                    self._session = await asyncio.wait_for(
                        self._cm.__aenter__(), timeout=self.settings.voice_provider_timeout
                    )
                    if "enable_affective_dialog" in candidate:
                        log.info("gemini live: affective dialog on", extra={"model": self._model})
                    break
                except Exception as exc:  # noqa: BLE001 — re-raised below when unretryable
                    last = exc
                    self._cm = None
                    self._session = None
                    if candidate is attempts[-1] or not _looks_like_setup_rejection(exc):
                        raise classify_gemini_error(exc) from exc
                    log.warning(
                        "gemini live rejected the humanising options, retrying without them",
                        extra={"error": str(exc)[:200]},
                    )
            if self._session is None and last is not None:      # pragma: no cover - defensive
                raise classify_gemini_error(last)
            self._closed.clear()
            log.info("gemini live session opened", extra={"model": self._model, "language": config.language})
        except Exception as exc:
            raise classify_gemini_error(exc) from exc

    async def close_session(self) -> None:
        self._closed.set()
        if self._cm is not None:
            with contextlib.suppress(Exception):
                await self._cm.__aexit__(None, None, None)
        self._cm = None
        self._session = None

    # ------------------------------------------------------------------ send

    async def send_audio(self, audio: AudioChunk) -> None:
        if self._session is None:
            raise ProviderInternalError("gemini live session is not open", provider="gemini")
        try:
            types = genai_types()
            await self._session.send_realtime_input(
                audio=types.Blob(data=audio.data, mime_type=f"audio/pcm;rate={audio.sample_rate}")
            )
        except Exception as exc:
            raise classify_gemini_error(exc) from exc

    async def send_text(self, text: str, *, role: str = "user", trigger_response: bool = True) -> None:
        if self._session is None:
            raise ProviderInternalError("gemini live session is not open", provider="gemini")
        try:
            await self._session.send_client_content(
                turns={"role": role, "parts": [{"text": text}]},
                turn_complete=trigger_response,
            )
        except Exception as exc:
            raise classify_gemini_error(exc) from exc

    async def interrupt(self) -> None:
        """Barge-in.

        Gemini cancels its own generation when server VAD hears the student.
        For an explicit Interrupt button we additionally mark activity so the
        model stops producing audio for the current turn. Client-side playback
        is stopped by the session manager without waiting for this call (§23).
        """
        if self._session is None:
            return
        with contextlib.suppress(Exception):
            await self._session.send_realtime_input(activity_start={})
            await self._session.send_realtime_input(activity_end={})

    # --------------------------------------------------------------- receive

    async def receive_events(self) -> AsyncIterator[ProviderEvent]:
        if self._session is None:
            raise ProviderInternalError("gemini live session is not open", provider="gemini")
        yield ProviderEvent(type=ProviderEventType.CONNECTED)
        try:
            while not self._closed.is_set():
                turn = self._session.receive()
                async for message in turn:
                    for event in self._map_message(message):
                        yield event
                        if event.type is ProviderEventType.TOOL_CALL and self._tool_handler:
                            await self._dispatch_tool(event)
        except Exception as exc:
            yield ProviderEvent(type=ProviderEventType.ERROR, error=classify_gemini_error(exc))
        finally:
            yield ProviderEvent(type=ProviderEventType.CLOSED)

    def _map_message(self, message: Any) -> list[ProviderEvent]:
        events: list[ProviderEvent] = []
        server_content = getattr(message, "server_content", None)

        if getattr(message, "data", None):
            events.append(ProviderEvent(type=ProviderEventType.AUDIO, audio=message.data))
        if getattr(message, "text", None):
            events.append(ProviderEvent(type=ProviderEventType.OUTPUT_TRANSCRIPT, text=message.text, partial=True))

        if server_content is not None:
            inp = getattr(server_content, "input_transcription", None)
            if inp is not None and getattr(inp, "text", None):
                events.append(
                    ProviderEvent(type=ProviderEventType.INPUT_TRANSCRIPT, text=inp.text, partial=True)
                )
            out = getattr(server_content, "output_transcription", None)
            if out is not None and getattr(out, "text", None):
                events.append(
                    ProviderEvent(type=ProviderEventType.OUTPUT_TRANSCRIPT, text=out.text, partial=True)
                )
            if getattr(server_content, "interrupted", False):
                events.append(ProviderEvent(type=ProviderEventType.INTERRUPTED))
            if getattr(server_content, "turn_complete", False):
                events.append(ProviderEvent(type=ProviderEventType.TURN_COMPLETE))
            if getattr(server_content, "generation_complete", False):
                events.append(ProviderEvent(type=ProviderEventType.TURN_COMPLETE))

        tool_call = getattr(message, "tool_call", None)
        if tool_call is not None:
            for fc in getattr(tool_call, "function_calls", []) or []:
                events.append(
                    ProviderEvent(
                        type=ProviderEventType.TOOL_CALL,
                        tool_name=getattr(fc, "name", None),
                        tool_args=dict(getattr(fc, "args", {}) or {}),
                        tool_call_id=getattr(fc, "id", None),
                    )
                )
        return events

    async def _dispatch_tool(self, event: ProviderEvent) -> None:
        if self._tool_handler is None or self._session is None or not event.tool_name:
            return
        try:
            result = await self._tool_handler(event.tool_name, event.tool_args or {})
        except Exception as exc:  # tool errors must never kill the call
            result = {"error": f"{type(exc).__name__}: {exc}"}
        with contextlib.suppress(Exception):
            types = genai_types()
            await self._session.send_tool_response(
                function_responses=[
                    types.FunctionResponse(
                        id=event.tool_call_id, name=event.tool_name, response=result
                    )
                ]
            )

    def set_tool_handler(self, handler: ToolHandler | None) -> None:
        self._tool_handler = handler


def _looks_like_setup_rejection(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(hint in text for hint in _SETUP_REJECTION_HINTS)
