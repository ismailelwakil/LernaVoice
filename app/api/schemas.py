"""Pydantic request/response models for the REST API (§35)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.learning.levels import is_known_level
from app.voice.dialects import arabic_dialect_options, normalise_dialect, split_language
from app.voice.state import SUPPORTED_LANGUAGES


class CreateSessionRequest(BaseModel):
    student_id: str = Field(min_length=1, max_length=128)
    language: str = "en"
    course_id: str | None = None
    lesson_id: str | None = None
    topic: str | None = None
    #: Catalogue topic id from GET /curriculum/courses (preferred over free text).
    topic_id: str | None = None
    document_ids: list[str] | None = None
    #: How to pitch the explanation: beginner | intermediate | advanced (also
    #: accepts a1/a2/b1/b2/c1/c2 and "first year"). Left out -> the level in the
    #: student's LERNA profile is used, and failing that the service default.
    level: str | None = None
    #: Arabic register. Arabic is taught in "ar-MSA" (fusHa) and every value
    #: resolves to it - older clients that still send "ar-EG" or "egyptian" are
    #: accepted and answered in fusHa. Ignored for the other nine languages.
    dialect: str | None = None
    resume_latest: bool = False

    @model_validator(mode="after")
    def _check_language(self) -> "CreateSessionRequest":
        """`ar`, `ar-MSA` and the older `ar-EG` all start a fusHa Arabic lesson."""
        language, register = split_language(self.language)
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(SUPPORTED_LANGUAGES)}")
        self.language = language
        # A register written into `language` wins only when `dialect` is silent.
        self.dialect = normalise_dialect(language, self.dialect or register)
        return self

    @model_validator(mode="after")
    def _check_level(self) -> "CreateSessionRequest":
        """An unknown level is a client bug, so say so instead of guessing."""
        if self.level is not None and not is_known_level(self.level):
            raise ValueError("level must be one of beginner, intermediate, advanced")
        return self


class SessionSummary(BaseModel):
    session_id: str
    student_id: str
    course_id: str | None = None
    lesson_id: str | None = None
    language: str
    dialect: str | None = None
    #: beginner | intermediate | advanced — the pitch of the explanation.
    student_level: str = "intermediate"
    state: str
    current_topic: str = ""
    current_section: str = ""
    topic_id: str | None = None
    lesson_plan: list[dict[str, str]] = []
    interrupt_count: int = 0
    resume_count: int = 0
    active_pipeline: dict[str, Any]
    created_at: float
    updated_at: float
    websocket_url: str | None = None


class SessionStateResponse(BaseModel):
    session_id: str
    state: str
    language: str
    dialect: str | None = None
    student_level: str = "intermediate"
    current_topic: str = ""
    current_section: str = ""
    topic_id: str | None = None
    lesson_plan: list[dict[str, str]] = []
    concepts_covered: list[str] = Field(default_factory=list)
    student_questions: list[dict[str, Any]] = Field(default_factory=list)
    interrupt_count: int = 0
    resume_count: int = 0
    is_returning: bool = False
    previous_session_id: str | None = None
    checkpoint: dict[str, Any] | None = None
    unresolved_questions: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    session_summary: str = ""
    next_action: str = ""
    active_pipeline: dict[str, Any]
    provider_history: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] | None = None
    #: What the tutor is teaching from: the vetted sources, the level's teaching
    #: moves and the closing question (see app/learning/explainer.py).
    explanation: dict[str, Any] | None = None


class InterruptResponse(BaseModel):
    session_id: str
    state: str
    checkpoint: dict[str, Any]
    acknowledgement: str
    playback_stop_ms: float | None = None


class QuestionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class QuestionResponse(BaseModel):
    session_id: str
    question_id: str
    is_followup: bool
    parent_question_id: str | None = None


class ResumeResponse(BaseModel):
    session_id: str
    state: str
    resumed_from: dict[str, Any] | None = None


class LanguageChangeRequest(BaseModel):
    #: Language code, or an Arabic register spelling (`ar-MSA`, `ar-EG`, `fusha`…).
    language: str
    #: Optional Arabic register, when the caller prefers to pass it separately.
    dialect: str | None = None

    @field_validator("language")
    @classmethod
    def _check(cls, v: str) -> str:
        body, _register = split_language(v)
        if body not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(SUPPORTED_LANGUAGES)}")
        return (v or "").strip()


class LevelChangeRequest(BaseModel):
    """A new pitch for the lesson being taught: beginner | intermediate | advanced."""

    level: str

    @model_validator(mode="after")
    def _check_level(self) -> "LevelChangeRequest":
        if not is_known_level(self.level):
            raise ValueError("level must be one of beginner, intermediate, advanced")
        return self


class SimpleResponse(BaseModel):
    session_id: str
    state: str
    detail: str = "ok"


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    service: str = "lerna-voice-ai"
    version: str = "1.0.0"
    # Operational shape, never credentials: which pipeline is in use and whether the
    # audio is coming from a real vendor or the offline mock. The demo screen uses
    # `mock_providers` to decide whether to voice the transcript itself.
    provider_mode: str = "auto"
    mock_providers: bool = False
    live_model: str | None = None
    gemini_auth: str = "none"
    #: Both auth paths, side by side: which model each one would connect to.
    live_models: dict[str, str] = {}
    #: The voice speaking the *offline* demo, e.g. "elevenlabs:eleven_v4_turbo".
    #: When set, the demo screen plays the service audio in "service" voice mode
    #: instead of voicing the transcript in the browser.
    demo_voice: str | None = None


class ErrorResponse(BaseModel):
    event: Literal["error"] = "error"
    code: str
    message: str
    recoverable: bool = True
