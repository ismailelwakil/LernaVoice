"""Progress Profile adapter (§30).

Reads LERNA's existing learner state and writes learning signals back into it.
It never maintains a second profile.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.lerna_bridge import LernaBridge, LernaUnavailable, get_bridge
from app.logging_setup import get_logger
from app.voice.state import LearningSignal

log = get_logger(__name__)

SIGNAL_KINDS = (
    "concept_discussed",
    "concept_understood",
    "question_asked",
    "misconception_detected",
    "concept_completed",
    "needs_reinforcement",
)


@dataclass(slots=True)
class LearnerContext:
    student_id: str
    name: str | None = None
    course: str | None = None
    preferred_language: str | None = None
    learning_preference: str | None = None
    #: beginner | intermediate | advanced — how the tutor should pitch it.
    level: str | None = None
    mastered: list[str] = field(default_factory=list)
    weak_concepts: list[str] = field(default_factory=list)
    prerequisite_gaps: list[str] = field(default_factory=list)
    misconceptions: list[str] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    available: bool = True
    note: str = ""

    def as_prompt_context(self) -> dict[str, Any]:
        return {
            "student_name": self.name,
            "student_level": self.level,
            "course": self.course,
            "learning_preference": self.learning_preference,
            "mastered_concepts": self.mastered[:10],
            "weak_concepts": self.weak_concepts[:10],
            "prerequisite_gaps": self.prerequisite_gaps[:10],
            "known_misconceptions": self.misconceptions[:10],
            "recent_topics": self.recent_topics[:6],
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "student_id": self.student_id,
            "available": self.available,
            "note": self.note,
            **self.as_prompt_context(),
        }


class ProgressProfileAdapter:
    def __init__(self, bridge: LernaBridge | None = None):
        self.bridge = bridge or get_bridge()

    async def get_context(self, student_id: str) -> LearnerContext:
        await self.bridge.ensure_ready()
        if not self.bridge.available:
            return LearnerContext(student_id=student_id, available=False, note="LERNA Progress Profile unavailable")
        try:
            if self.bridge.mode == "inprocess":
                profile = await self.bridge.call_inprocess("get_learning_profile", student_id)
            else:
                profile = await self.bridge.call_http("GET", f"/students/{student_id}/profile")
            return _to_context(student_id, profile)
        except LernaUnavailable as exc:
            return LearnerContext(student_id=student_id, available=False, note=str(exc))
        except Exception as exc:
            log.warning("progress profile read failed", extra={"error_type": type(exc).__name__})
            return LearnerContext(student_id=student_id, available=False, note=type(exc).__name__)

    async def record_signal(self, student_id: str, signal: LearningSignal, *, session_id: str | None = None) -> bool:
        """Append a voice learning signal to the student's existing profile."""
        await self.bridge.ensure_ready()
        if not self.bridge.available or self.bridge.mode != "inprocess":
            return False
        try:
            module = self.bridge.module
            tutor = getattr(module, "tutor", None)
            store = getattr(tutor, "store", None)
            if store is None:
                return False
            import asyncio

            def _write() -> bool:
                profile = store.load(student_id)
                if profile is None:
                    return False
                entry = {
                    "source": "voice_tutor",
                    "session_id": session_id,
                    "signal": signal.kind,
                    "concept": signal.concept,
                    "detail": signal.detail,
                    "confidence": signal.confidence,
                    "timestamp": time.time(),
                }
                profile.learning_history.append(entry)
                if signal.kind == "misconception_detected" and signal.concept not in profile.misconceptions:
                    profile.misconceptions.append(signal.concept)
                if signal.kind == "needs_reinforcement" and signal.concept not in profile.weak_concepts:
                    profile.weak_concepts.append(signal.concept)
                if signal.kind in ("concept_discussed", "concept_completed"):
                    if signal.concept and signal.concept not in profile.recent_topics:
                        profile.recent_topics.insert(0, signal.concept)
                        profile.recent_topics = profile.recent_topics[:20]
                store.save(profile)
                return True

            return await asyncio.to_thread(_write)
        except Exception as exc:
            log.warning("learning signal write failed", extra={"error_type": type(exc).__name__})
            return False


def _to_context(student_id: str, profile: Any) -> LearnerContext:
    if profile is None:
        return LearnerContext(student_id=student_id, available=False, note="profile not found")
    get = profile.get if isinstance(profile, dict) else lambda k, d=None: getattr(profile, k, d)
    student = get("student", None)
    sget = (
        student.get
        if isinstance(student, dict)
        else (lambda k, d=None: getattr(student, k, d))
        if student is not None
        else (lambda k, d=None: d)
    )
    mastery = get("concept_mastery", {}) or {}
    mastered = [c for c, v in mastery.items() if isinstance(v, (int, float)) and v >= 0.8]
    return LearnerContext(
        student_id=student_id,
        name=sget("name", None),
        course=sget("course", None) or get("course", None),
        preferred_language=sget("preferred_language", None),
        learning_preference=sget("learning_preference", None),
        level=(
            sget("level", None)
            or sget("education_level", None)
            or get("level", None)
            or get("student_level", None)
            or get("proficiency", None)
        ),
        mastered=mastered,
        weak_concepts=list(get("weak_concepts", []) or []),
        prerequisite_gaps=list(get("prerequisite_gaps", []) or []),
        misconceptions=list(get("misconceptions", []) or []),
        recent_topics=list(get("recent_topics", []) or []),
        available=True,
    )
