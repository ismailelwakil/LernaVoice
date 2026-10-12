"""Provider-independent interfaces (§6).

The application layer only ever talks to these abstractions. No `if provider ==
"gemini"` branching is allowed above this package.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Awaitable


# --------------------------------------------------------------------------- #
# errors
# --------------------------------------------------------------------------- #


class ErrorClass(str, Enum):
    TEMPORARY = "temporary"
    RECOVERABLE = "recoverable"
    NON_RECOVERABLE = "non_recoverable"
    UNSUPPORTED = "unsupported"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"


class ProviderError(Exception):
    """Base class for every provider failure, always classified."""

    error_class: ErrorClass = ErrorClass.RECOVERABLE

    def __init__(self, message: str, *, provider: str = "unknown", retryable: bool | None = None):
        super().__init__(message)
        self.provider = provider
        self.message = message
        self._retryable = retryable

    @property
    def retryable(self) -> bool:
        if self._retryable is not None:
            return self._retryable
        return self.error_class in (ErrorClass.TEMPORARY, ErrorClass.RECOVERABLE, ErrorClass.RATE_LIMIT)

    @property
    def should_failover(self) -> bool:
        return self.error_class is not ErrorClass.UNSUPPORTED

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<{type(self).__name__} provider={self.provider} class={self.error_class.value}>"


class ProviderTimeoutError(ProviderError):
    error_class = ErrorClass.TEMPORARY


class ProviderNetworkError(ProviderError):
    error_class = ErrorClass.TEMPORARY


class ProviderRateLimitError(ProviderError):
    error_class = ErrorClass.RATE_LIMIT


class ProviderQuotaError(ProviderError):
    error_class = ErrorClass.QUOTA

    @property
    def retryable(self) -> bool:
        return False


class ProviderAuthError(ProviderError):
    error_class = ErrorClass.AUTHENTICATION

    @property
    def retryable(self) -> bool:
        return False


class ProviderUnsupportedError(ProviderError):
    error_class = ErrorClass.UNSUPPORTED

    @property
    def retryable(self) -> bool:
        return False


class ProviderInternalError(ProviderError):
    error_class = ErrorClass.RECOVERABLE


class MalformedAudioError(ProviderError):
    error_class = ErrorClass.NON_RECOVERABLE

    @property
    def retryable(self) -> bool:
        return False


# --------------------------------------------------------------------------- #
# value objects
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class AudioChunk:
    """Raw little-endian 16-bit PCM."""

    data: bytes
    sample_rate: int = 16000
    channels: int = 1

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.data)


@dataclass(slots=True)
class SessionConfig:
    """Everything a provider needs to open a conversation."""

    session_id: str
    language: str
    system_instruction: str
    voice_name: str | None = None
    input_sample_rate: int = 16000
    output_sample_rate: int = 24000
    tools: list[dict[str, Any]] = field(default_factory=list)
    initial_context: list[dict[str, str]] = field(default_factory=list)
    temperature: float = 0.7
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderEventType(str, Enum):
    CONNECTED = "connected"
    INPUT_TRANSCRIPT = "input_transcript"
    OUTPUT_TRANSCRIPT = "output_transcript"
    AUDIO = "audio"
    TURN_STARTED = "turn_started"
    TURN_COMPLETE = "turn_complete"
    INTERRUPTED = "interrupted"
    TOOL_CALL = "tool_call"
    SPEECH_STARTED = "speech_started"
    SPEECH_STOPPED = "speech_stopped"
    ERROR = "error"
    CLOSED = "closed"


@dataclass(slots=True)
class ProviderEvent:
    type: ProviderEventType
    text: str | None = None
    audio: bytes | None = None
    partial: bool = False
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_call_id: str | None = None
    error: ProviderError | None = None
    ts: float = field(default_factory=time.time)
    raw: dict[str, Any] | None = None


ToolHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


# --------------------------------------------------------------------------- #
# component interfaces
# --------------------------------------------------------------------------- #


class VoiceComponent(ABC):
    """Common base so health/telemetry code can treat all pieces alike."""

    provider_name: str = "unknown"
    role: str = "component"

    async def aclose(self) -> None:
        return None


class SpeechToTextProvider(VoiceComponent):
    role = "stt"

    @abstractmethod
    async def start_stream(self, language: str, sample_rate: int = 16000) -> None: ...

    @abstractmethod
    async def send_audio(self, chunk: AudioChunk) -> None: ...

    @abstractmethod
    async def receive_events(self) -> AsyncIterator[ProviderEvent]: ...

    @abstractmethod
    async def finalize(self) -> None:
        """Signal end-of-utterance; provider should emit a final transcript."""

    @abstractmethod
    async def stop_stream(self) -> None: ...


class TextToSpeechProvider(VoiceComponent):
    role = "tts"

    @abstractmethod
    async def synthesize_stream(
        self, text: str, language: str, *, voice: str | None = None
    ) -> AsyncIterator[AudioChunk]:
        """Yield audio chunks as they are produced (streaming where supported)."""

    async def cancel(self) -> None:
        """Best-effort cancellation of in-flight synthesis (barge-in)."""
        return None


class LLMProvider(VoiceComponent):
    role = "llm"

    @abstractmethod
    async def stream_reply(
        self,
        messages: list[dict[str, str]],
        *,
        system_instruction: str,
        language: str,
        tools: list[dict[str, Any]] | None = None,
        tool_handler: ToolHandler | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        """Stream OUTPUT_TRANSCRIPT deltas and TOOL_CALL events.

        `metadata` carries the session's lesson plan (topic, sections) for
        components that generate the tutor's words in a composed pipeline, where
        the realtime provider that received SessionConfig is not the one talking.
        Real vendors ignore it; the system instruction already states the plan.
        """

    async def cancel(self) -> None:
        return None


class RealtimeVoiceProvider(VoiceComponent):
    """Speech-in / speech-out conversation (§6)."""

    role = "realtime"
    supports_native_interruption: bool = False
    supports_turn_detection: bool = False

    @abstractmethod
    async def start_session(self, config: SessionConfig) -> None: ...

    @abstractmethod
    async def send_audio(self, audio: AudioChunk) -> None: ...

    @abstractmethod
    async def send_text(self, text: str, *, role: str = "user", trigger_response: bool = True) -> None: ...

    @abstractmethod
    async def receive_events(self) -> AsyncIterator[ProviderEvent]: ...

    @abstractmethod
    async def interrupt(self) -> None: ...

    @abstractmethod
    async def close_session(self) -> None: ...

    def set_tool_handler(self, handler: ToolHandler | None) -> None:
        self._tool_handler = handler


# Alias kept because the spec names both (§6).
RealtimeConversationProvider = RealtimeVoiceProvider
