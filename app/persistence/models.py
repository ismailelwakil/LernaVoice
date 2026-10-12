"""Persistence document shapes (§27, §49).

The LERNA platform persists with MongoDB, so the voice service adds five
namespaced collections rather than a parallel database:

    voice_sessions         one document per voice session (the full state)
    voice_checkpoints      every learning checkpoint ever created
    voice_interactions     turn-by-turn transcript records
    voice_questions        student questions and their answers
    voice_provider_events  provider selection / failure / switch audit trail

Raw audio is never written to any of them (§50).
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from app.voice.state import VoiceSessionState

SESSIONS = "voice_sessions"
CHECKPOINTS = "voice_checkpoints"
INTERACTIONS = "voice_interactions"
QUESTIONS = "voice_questions"
PROVIDER_EVENTS = "voice_provider_events"

ALL_COLLECTIONS = (SESSIONS, CHECKPOINTS, INTERACTIONS, QUESTIONS, PROVIDER_EVENTS)


class ProviderEventDoc(BaseModel):
    session_id: str
    student_id: str | None = None
    kind: str  # selected | connected | failed | retrying | fallback_started | switched
    from_pipeline: str | None = None
    to_pipeline: str | None = None
    provider: str | None = None
    reason: str | None = None
    error_class: str | None = None
    retry_count: int = 0
    timestamp: float = Field(default_factory=time.time)


class InteractionDoc(BaseModel):
    session_id: str
    student_id: str
    interaction_id: str
    role: str
    kind: str
    text: str
    language: str
    pipeline: str | None = None
    timestamp: float = Field(default_factory=time.time)


class QuestionDoc(BaseModel):
    session_id: str
    student_id: str
    question_id: str
    text: str
    language: str
    answered: bool = False
    answer: str | None = None
    is_followup: bool = False
    parent_question_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    asked_at: float = Field(default_factory=time.time)
    answered_at: float | None = None


class CheckpointDoc(BaseModel):
    session_id: str
    student_id: str
    checkpoint_id: str
    topic: str
    section: str
    concepts_covered: list[str] = Field(default_factory=list)
    last_concept: str | None = None
    next_concept: str | None = None
    resume_instruction: str = ""
    reason: str = "interrupt"
    created_at: float = Field(default_factory=time.time)


def session_to_document(state: VoiceSessionState) -> dict[str, Any]:
    doc = state.model_dump(mode="json")
    doc["_id"] = state.session_id
    return doc


def document_to_session(doc: dict[str, Any]) -> VoiceSessionState:
    data = {k: v for k, v in doc.items() if k != "_id"}
    return VoiceSessionState.model_validate(data)
