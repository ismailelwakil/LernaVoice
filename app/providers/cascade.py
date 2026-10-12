"""Composed STT -> LLM -> TTS pipeline presented as a RealtimeVoiceProvider (§11).

This is how a vendor that only covers part of the stack (ElevenLabs, Deepgram)
becomes a usable voice tutor without the application layer ever knowing. It is
genuinely streaming: partial transcripts arrive as the student speaks, the LLM
is streamed token by token, and each completed sentence is sent to TTS
immediately rather than waiting for the full answer.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from typing import Any, AsyncIterator

from app.logging_setup import get_logger
from app.providers.base import (
    AudioChunk,
    LLMProvider,
    ProviderError,
    ProviderEvent,
    ProviderEventType,
    ProviderInternalError,
    RealtimeVoiceProvider,
    SessionConfig,
    SpeechToTextProvider,
    TextToSpeechProvider,
    ToolHandler,
)

log = get_logger(__name__)

_SENTENCE_END = re.compile(r"(?<=[.!?؟。！？…:;])\s+|\n+")
MIN_SPEAK_CHARS = 60


class CascadePipelineProvider(RealtimeVoiceProvider):
    """STT + LLM + TTS behaving like one realtime conversation provider."""

    supports_native_interruption = False  # emulated: cancel generation + TTS
    supports_turn_detection = True  # provided by the STT component's VAD

    def __init__(
        self,
        stt: SpeechToTextProvider,
        llm: LLMProvider,
        tts: TextToSpeechProvider,
        *,
        name: str | None = None,
        tts_fallbacks: list[TextToSpeechProvider] | None = None,
    ):
        self.stt = stt
        self.llm = llm
        self.tts = tts
        #: Round 27 — backup voices tried in order if the active voice fails before
        #: it has spoken (e.g. Azure is down → Fish Audio speaks instead).
        self.tts_fallbacks: list[TextToSpeechProvider] = list(tts_fallbacks or [])
        self.voice_vendor: str | None = None
        self.provider_name = name or f"{stt.provider_name}+{llm.provider_name}+{tts.provider_name}"
        self.role = "realtime"

        self._config: SessionConfig | None = None
        self._messages: list[dict[str, str]] = []
        self.sent_text: list[str] = []  # observability: prompts handed to the pipeline
        self._out: asyncio.Queue[ProviderEvent | None] = asyncio.Queue()
        self._stt_task: asyncio.Task | None = None
        self._gen_task: asyncio.Task | None = None
        self._tool_handler: ToolHandler | None = None
        self._interrupted = asyncio.Event()
        self._open = False

    def attach_tts(self, tts, vendor: str) -> None:
        """Let a real vendor voice an otherwise-offline pipeline (demo_voice.py)."""
        self.tts = tts
        self.voice_vendor = vendor

    # ------------------------------------------------------------- lifecycle

    async def start_session(self, config: SessionConfig) -> None:
        self._config = config
        self._messages = [dict(m) for m in config.initial_context]
        _context = getattr(self.tts, "set_language_context", None)
        if _context is not None:
            _context(config.language, (config.metadata or {}).get("dialect"))
        await self.stt.start_stream(config.language, config.input_sample_rate)
        self._stt_task = asyncio.create_task(self._consume_stt())
        self._open = True
        await self._out.put(ProviderEvent(type=ProviderEventType.CONNECTED))

    async def close_session(self) -> None:
        self._open = False
        await self._cancel_generation()
        if self._stt_task:
            self._stt_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._stt_task
            self._stt_task = None
        with contextlib.suppress(Exception):
            await self.stt.stop_stream()
        await self._out.put(None)

    # ------------------------------------------------------------------ send

    async def send_audio(self, audio: AudioChunk) -> None:
        if not self._open:
            raise ProviderInternalError("cascade session is not open", provider=self.provider_name)
        await self.stt.send_audio(audio)

    async def send_text(self, text: str, *, role: str = "user", trigger_response: bool = True) -> None:
        if not self._open:
            raise ProviderInternalError("cascade session is not open", provider=self.provider_name)
        self._messages.append({"role": "user" if role == "user" else "assistant", "content": text})
        self.sent_text.append(text)
        if trigger_response:
            await self._start_generation()

    async def interrupt(self) -> None:
        self._interrupted.set()
        await self._cancel_generation()
        with contextlib.suppress(Exception):
            await self.tts.cancel()
        with contextlib.suppress(Exception):
            await self.llm.cancel()
        await self._out.put(ProviderEvent(type=ProviderEventType.INTERRUPTED))

    # --------------------------------------------------------------- receive

    async def receive_events(self) -> AsyncIterator[ProviderEvent]:
        while True:
            event = await self._out.get()
            if event is None:
                return
            yield event

    def set_tool_handler(self, handler: ToolHandler | None) -> None:
        self._tool_handler = handler

    # ------------------------------------------------------------- internals

    async def _consume_stt(self) -> None:
        try:
            async for event in self.stt.receive_events():
                if event.type is ProviderEventType.INPUT_TRANSCRIPT:
                    await self._out.put(event)
                    if not event.partial and (event.text or "").strip():
                        self._messages.append({"role": "user", "content": event.text.strip()})
                        await self._start_generation()
                elif event.type in (
                    ProviderEventType.SPEECH_STARTED,
                    ProviderEventType.SPEECH_STOPPED,
                    ProviderEventType.ERROR,
                ):
                    await self._out.put(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._out.put(
                ProviderEvent(
                    type=ProviderEventType.ERROR,
                    error=exc if isinstance(exc, ProviderError) else ProviderInternalError(str(exc), provider=self.provider_name),
                )
            )

    async def _cancel_generation(self) -> None:
        if self._gen_task and not self._gen_task.done():
            self._gen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._gen_task
        self._gen_task = None

    async def _start_generation(self) -> None:
        await self._cancel_generation()
        self._interrupted.clear()
        self._gen_task = asyncio.create_task(self._generate())

    async def _generate(self) -> None:
        assert self._config is not None
        config = self._config
        await self._out.put(ProviderEvent(type=ProviderEventType.TURN_STARTED))
        buffer = ""
        spoken: list[str] = []
        full: list[str] = []
        try:
            async for event in self.llm.stream_reply(
                self._messages,
                system_instruction=config.system_instruction,
                language=config.language,
                tools=config.tools or None,
                tool_handler=self._tool_handler,
                metadata=config.metadata,
            ):
                if self._interrupted.is_set():
                    return
                if event.type is ProviderEventType.TOOL_CALL:
                    await self._out.put(event)
                    continue
                if event.type is ProviderEventType.OUTPUT_TRANSCRIPT and event.text:
                    full.append(event.text)
                    buffer += event.text
                    await self._out.put(event)
                    sentence, buffer = _take_sentence(buffer)
                    if sentence:
                        spoken.append(sentence)
                        await self._speak(sentence, config.language)
                elif event.type is ProviderEventType.TURN_COMPLETE:
                    if event.text and not full:
                        full.append(event.text)
                        buffer = event.text

            tail = buffer.strip()
            if tail and not self._interrupted.is_set():
                spoken.append(tail)
                await self._speak(tail, config.language)

            answer = "".join(full).strip()
            if answer:
                self._messages.append({"role": "assistant", "content": answer})
            await self._out.put(ProviderEvent(type=ProviderEventType.TURN_COMPLETE, text=answer))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._out.put(
                ProviderEvent(
                    type=ProviderEventType.ERROR,
                    error=exc if isinstance(exc, ProviderError) else ProviderInternalError(str(exc), provider=self.provider_name),
                )
            )

    async def _speak(self, text: str, language: str) -> None:
        # Try the active voice, then each backup — but only fail over if the voice
        # broke *before* speaking (auth/outage). A mid-line failure is surfaced as an
        # error rather than restarted, so the student never hears the line twice.
        voices = [self.tts, *self.tts_fallbacks]
        last_exc: Exception | None = None
        for index, tts in enumerate(voices):
            if tts is None:
                continue
            emitted = False
            try:
                ctx = getattr(tts, "set_language_context", None)
                if ctx is not None:
                    ctx(language, getattr(self, "_dialect", None))
                async for chunk in tts.synthesize_stream(text, language):
                    if self._interrupted.is_set():
                        return
                    emitted = True
                    await self._out.put(ProviderEvent(type=ProviderEventType.AUDIO, audio=chunk.data))
                return  # this voice spoke the whole line
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if emitted:
                    break  # spoke part of it; don't duplicate by restarting
                if index + 1 < len(voices):
                    log.warning(
                        "TTS %s failed before speaking (%s); failing over to backup voice",
                        getattr(tts, "provider_name", "?"), type(exc).__name__,
                    )
                    continue
        await self._out.put(
            ProviderEvent(
                type=ProviderEventType.ERROR,
                error=last_exc if isinstance(last_exc, ProviderError)
                else ProviderInternalError(str(last_exc), provider=self.provider_name),
            )
        )

    async def aclose(self) -> None:
        await self.close_session()


def _take_sentence(buffer: str) -> tuple[str, str]:
    """Pull one speakable sentence off the buffer once it is long enough."""
    if len(buffer) < MIN_SPEAK_CHARS:
        return "", buffer
    matches = list(_SENTENCE_END.finditer(buffer))
    if not matches:
        return "", buffer
    cut = matches[-1].end()
    sentence = buffer[:cut].strip()
    return (sentence, buffer[cut:]) if sentence else ("", buffer)
