"""Provider-independent realtime event model.

Every event emitted on the WebSocket is one of EventType. See
docs/WEBSOCKET_PROTOCOL.md for the full contract.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    # session lifecycle
    SESSION_STARTED = "session.started"
    SESSION_STATE_CHANGED = "session.state_changed"
    SESSION_PAUSED = "session.paused"
    SESSION_RESUMED = "session.resumed"
    SESSION_ENDED = "session.ended"
    SESSION_RECAP = "session.recap"

    # student audio
    AUDIO_INPUT_STARTED = "audio.input.started"
    AUDIO_INPUT_CHUNK = "audio.input.chunk"
    AUDIO_INPUT_ENDED = "audio.input.ended"
    INPUT_TRANSCRIPT = "input.transcript"

    # assistant output
    ASSISTANT_RESPONSE_STARTED = "assistant.response.started"
    ASSISTANT_TEXT_DELTA = "assistant.text.delta"
    ASSISTANT_AUDIO_CHUNK = "assistant.audio.chunk"
    ASSISTANT_RESPONSE_COMPLETED = "assistant.response.completed"
    ASSISTANT_INTERRUPTED = "assistant.interrupted"

    # tutoring flow
    QUESTION_STARTED = "question.started"
    QUESTION_COMPLETED = "question.completed"
    CHECKPOINT_CREATED = "checkpoint.created"
    RESUME_STARTED = "resume.started"
    RESUME_COMPLETED = "resume.completed"
    LANGUAGE_CHANGED = "language.changed"
    #: The grounded, level-adapted explanation the tutor teaches from.
    EXPLANATION_PLANNED = "explanation.planned"
    LEARNING_SIGNAL = "learning.signal"
    VISUAL_UPDATED = "visual.updated"
    RAG_RETRIEVED = "rag.retrieved"

    # provider lifecycle
    PROVIDER_SELECTED = "provider.selected"
    PROVIDER_CONNECTED = "provider.connected"
    PROVIDER_FAILED = "provider.failed"
    PROVIDER_RETRYING = "provider.retrying"
    PROVIDER_FALLBACK_STARTED = "provider.fallback_started"
    PROVIDER_SWITCHED = "provider.switched"

    # diagnostics
    LATENCY = "latency"
    ERROR = "error"
    PONG = "pong"


class VoiceEvent(BaseModel):
    """Envelope for everything the service pushes to a client."""

    event: EventType
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:16]}")
    session_id: str | None = None
    ts: float = Field(default_factory=time.time)
    seq: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        payload = {
            "event": self.event.value,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "ts": self.ts,
            **self.data,
        }
        if self.seq is not None:
            payload["seq"] = self.seq
        return payload


def make_event(event: EventType, session_id: str | None = None, **data: Any) -> VoiceEvent:
    return VoiceEvent(event=event, session_id=session_id, data=data)


# ---------------------------------------------------------------- error codes


class ErrorCode(str, Enum):
    VOICE_PROVIDER_UNAVAILABLE = "VOICE_PROVIDER_UNAVAILABLE"
    VOICE_PROVIDER_TIMEOUT = "VOICE_PROVIDER_TIMEOUT"
    VOICE_PROVIDER_RATE_LIMITED = "VOICE_PROVIDER_RATE_LIMITED"
    VOICE_PROVIDER_QUOTA_EXHAUSTED = "VOICE_PROVIDER_QUOTA_EXHAUSTED"
    VOICE_PROVIDER_AUTH_FAILED = "VOICE_PROVIDER_AUTH_FAILED"
    VOICE_LANGUAGE_UNSUPPORTED = "VOICE_LANGUAGE_UNSUPPORTED"
    VOICE_CAPABILITY_UNSUPPORTED = "VOICE_CAPABILITY_UNSUPPORTED"
    VOICE_AUDIO_MALFORMED = "VOICE_AUDIO_MALFORMED"
    VOICE_SESSION_NOT_FOUND = "VOICE_SESSION_NOT_FOUND"
    VOICE_SESSION_INVALID_STATE = "VOICE_SESSION_INVALID_STATE"
    VOICE_AUTH_REQUIRED = "VOICE_AUTH_REQUIRED"
    VOICE_RAG_UNAVAILABLE = "VOICE_RAG_UNAVAILABLE"
    VOICE_PERSISTENCE_UNAVAILABLE = "VOICE_PERSISTENCE_UNAVAILABLE"
    VOICE_CONNECTION_LOST = "VOICE_CONNECTION_LOST"
    VOICE_INTERNAL_ERROR = "VOICE_INTERNAL_ERROR"


def error_event(
    code: ErrorCode,
    message: str,
    *,
    recoverable: bool = True,
    session_id: str | None = None,
    **extra: Any,
) -> VoiceEvent:
    return make_event(
        EventType.ERROR,
        session_id=session_id,
        code=code.value,
        message=message,
        recoverable=recoverable,
        **extra,
    )
