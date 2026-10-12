"""Structured voice session state (§22) and learning checkpoints (§24)."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "ar", "fr", "sw", "am", "ha", "so", "yo", "ig", "zu")

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "ar": "Arabic",
    "fr": "French",
    "sw": "Swahili",
    "am": "Amharic",
    "ha": "Hausa",
    "so": "Somali",
    "yo": "Yoruba",
    "ig": "Igbo",
    "zu": "Zulu",
}


class SessionState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ANSWERING = "answering"
    RESUMING = "resuming"
    PAUSED = "paused"
    ENDED = "ended"
    ERROR = "error"


def _now() -> float:
    return time.time()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class ActivePipeline(BaseModel):
    """Which vendor serves each role right now (§11 provider composition)."""

    mode: Literal["realtime", "cascade"] = "realtime"
    stt: str = "gemini"
    llm: str = "gemini"
    tts: str = "gemini"
    realtime: str | None = "gemini"

    def signature(self) -> str:
        if self.mode == "realtime":
            return f"realtime:{self.realtime}"
        return f"cascade:{self.stt}+{self.llm}+{self.tts}"


class ProviderTransition(BaseModel):
    from_pipeline: str | None = None
    to_pipeline: str
    reason: str
    timestamp: float = Field(default_factory=_now)


class LessonCheckpoint(BaseModel):
    """A *learning* checkpoint, not an audio timestamp (§24)."""

    checkpoint_id: str = Field(default_factory=lambda: new_id("ckpt"))
    topic: str = ""
    section: str = ""
    concepts_covered: list[str] = Field(default_factory=list)
    last_concept: str | None = None
    next_concept: str | None = None
    resume_instruction: str = ""
    spoken_so_far: str = ""
    created_at: float = Field(default_factory=_now)
    reason: str = "interrupt"


class StudentQuestionRecord(BaseModel):
    question_id: str = Field(default_factory=lambda: new_id("q"))
    text: str
    language: str = "en"
    answered: bool = False
    answer: str | None = None
    is_followup: bool = False
    parent_question_id: str | None = None
    asked_at: float = Field(default_factory=_now)
    answered_at: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class LearningSignal(BaseModel):
    kind: Literal[
        "concept_discussed",
        "concept_understood",
        "question_asked",
        "misconception_detected",
        "concept_completed",
        "needs_reinforcement",
    ]
    concept: str
    detail: str | None = None
    confidence: float = 0.5
    #: What the tutor actually said, when it was not English (learning state is
    #: stored in the catalogue's English wording; see canonical_concepts.py).
    spoken_as: str | None = None
    #: Session language at the time, and whether `concept` was resolved to English.
    language: str | None = None
    canonical: bool = True
    #: Curriculum phrase this concept maps onto, when one matches.
    catalogue_ref: str | None = None
    ts: float = Field(default_factory=_now)


class VisualPayload(BaseModel):
    type: Literal["code", "equation", "diagram", "table", "image", "text"]
    content: str
    language: str | None = None
    caption: str | None = None


class InteractionRecord(BaseModel):
    interaction_id: str = Field(default_factory=lambda: new_id("int"))
    role: Literal["student", "tutor", "system"]
    text: str
    language: str = "en"
    pipeline: str | None = None
    ts: float = Field(default_factory=_now)
    kind: Literal["lesson", "question", "answer", "resume", "recap", "system"] = "lesson"


class VoiceSessionState(BaseModel):
    """Full persisted session document."""

    session_id: str = Field(default_factory=lambda: new_id("vs"))
    student_id: str
    course_id: str | None = None
    lesson_id: str | None = None
    language: str = "en"
    #: Arabic only: the register the tutor speaks — `ar-MSA` (fusHa) today. An
    #: older client may still send `ar-EG`; it normalises to `ar-MSA`. The language
    #: code stays `ar` for routing and learning state; this only decides the voice,
    #: the phrase set and the sentence the instruction adds.
    dialect: str | None = None
    #: How this student is taught: beginner | intermediate | advanced. Read from the
    #: LERNA Progress Profile (a local mirror until that integration is live, see
    #: app/learner/profiles.py); it decides the moves of the explanation.
    student_level: str = "intermediate"
    state: SessionState = SessionState.IDLE

    current_topic: str = ""
    current_section: str = ""
    #: Catalogue topic this session teaches (see app/curriculum.py). The plan is
    #: section-by-section so checkpoints reference real lesson steps.
    topic_id: str | None = None
    lesson_plan: list[dict[str, str]] = Field(default_factory=list)
    #: The grounding the tutor was given for this topic: the vetted sources and the
    #: level-adapted moves (see app/learning/explainer.py). Persisted, so a resumed
    #: session keeps explaining the same way.
    explanation: dict | None = None
    resume_checkpoint: LessonCheckpoint | None = None
    checkpoints: list[LessonCheckpoint] = Field(default_factory=list)

    concepts_covered: list[str] = Field(default_factory=list)
    student_questions: list[StudentQuestionRecord] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    #: Canonical (English) misconceptions; the Arabic/French wording stays on the
    #: learning signal that produced them.
    misconceptions: list[str] = Field(default_factory=list)
    learning_signals: list[LearningSignal] = Field(default_factory=list)
    interactions: list[InteractionRecord] = Field(default_factory=list)

    session_summary: str = ""
    next_action: str = ""

    active_pipeline: ActivePipeline = Field(default_factory=ActivePipeline)
    provider_history: list[ProviderTransition] = Field(default_factory=list)

    interrupt_count: int = 0
    resume_count: int = 0

    # returning-student linkage (§28)
    is_returning: bool = False
    previous_session_id: str | None = None
    document_ids: list[str] | None = None

    created_at: float = Field(default_factory=_now)
    updated_at: float = Field(default_factory=_now)
    ended_at: float | None = None

    # ------------------------------------------------------------------ utils

    def touch(self) -> None:
        self.updated_at = _now()

    def add_concept(self, concept: str) -> None:
        c = (concept or "").strip()
        if c and c not in self.concepts_covered:
            self.concepts_covered.append(c)

    def record_interaction(self, record: InteractionRecord) -> None:
        self.interactions.append(record)
        # Keep the hot document bounded; full history lives in voice_interactions.
        if len(self.interactions) > 200:
            self.interactions = self.interactions[-200:]
        self.touch()

    def open_questions(self) -> list[StudentQuestionRecord]:
        return [q for q in self.student_questions if not q.answered]

    def last_question(self) -> StudentQuestionRecord | None:
        return self.student_questions[-1] if self.student_questions else None

    def switch_pipeline(self, pipeline: ActivePipeline, reason: str) -> ProviderTransition:
        transition = ProviderTransition(
            from_pipeline=self.active_pipeline.signature() if self.active_pipeline else None,
            to_pipeline=pipeline.signature(),
            reason=reason,
        )
        self.provider_history.append(transition)
        self.active_pipeline = pipeline
        self.touch()
        return transition

    def to_public(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        return data
