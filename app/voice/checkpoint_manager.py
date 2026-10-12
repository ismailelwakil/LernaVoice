"""Learning checkpoints (§24) — progress, not an audio timestamp.

The checkpoint is derived from what the tutor actually said plus the concepts
the model reported through the `record_learning_signal` tool. A deterministic
extractor runs first so a checkpoint ALWAYS exists even when a provider dies
mid-sentence; an LLM refinement can improve it when one is available.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.learner.canonical_concepts import canonicalise_concept
from app.logging_setup import get_logger
from app.persistence.models import CheckpointDoc
from app.persistence.repository import VoiceRepository
from app.voice.state import LessonCheckpoint, VoiceSessionState

log = get_logger(__name__)

_SENTENCES = re.compile(r"(?<=[.!?؟。！？])\s+|\n+")


class CheckpointManager:
    def __init__(self, repository: VoiceRepository):
        self.repository = repository

    async def create(
        self,
        state: VoiceSessionState,
        *,
        spoken_transcript: str,
        reason: str = "interrupt",
    ) -> LessonCheckpoint:
        checkpoint = self._extract(state, spoken_transcript, reason)
        state.resume_checkpoint = checkpoint
        state.checkpoints.append(checkpoint)
        if len(state.checkpoints) > 50:
            state.checkpoints = state.checkpoints[-50:]
        state.current_topic = checkpoint.topic or state.current_topic
        state.current_section = checkpoint.section or state.current_section
        state.touch()
        try:
            await self.repository.append_checkpoint(
                CheckpointDoc(
                    session_id=state.session_id,
                    student_id=state.student_id,
                    checkpoint_id=checkpoint.checkpoint_id,
                    topic=checkpoint.topic,
                    section=checkpoint.section,
                    concepts_covered=list(checkpoint.concepts_covered),
                    last_concept=checkpoint.last_concept,
                    next_concept=checkpoint.next_concept,
                    resume_instruction=checkpoint.resume_instruction,
                    reason=reason,
                )
            )
        except Exception as exc:
            log.warning("checkpoint persistence failed", extra={"error_type": type(exc).__name__})
        return checkpoint

    # ------------------------------------------------------------ extraction

    def _extract(self, state: VoiceSessionState, transcript: str, reason: str) -> LessonCheckpoint:
        text = " ".join((transcript or "").split())
        sentences = [s.strip() for s in _SENTENCES.split(text) if s.strip()]
        covered = list(state.concepts_covered)
        previous = state.resume_checkpoint

        if covered:
            last_concept = covered[-1]
        elif sentences:
            # The plan's own wording may be realised in the session language; the
            # checkpoint still stores the concept the way the catalogue names it.
            last_concept = canonicalise_concept(
                sentences[-1][:120], language=state.language, topic_id=state.topic_id
            ).canonical
        else:
            last_concept = None
        section = state.current_section or (sentences[-1][:80] if sentences else "")
        topic = state.current_topic or (previous.topic if previous else "")

        next_concept = None
        if previous and previous.next_concept and previous.next_concept != last_concept:
            next_concept = previous.next_concept

        resume_instruction = (
            f"Continue from '{last_concept}'." if last_concept else "Continue the lesson from where it stopped."
        )
        if next_concept:
            resume_instruction = f"Continue by explaining '{next_concept}'."

        return LessonCheckpoint(
            topic=topic,
            section=section,
            concepts_covered=covered,
            last_concept=last_concept,
            next_concept=next_concept,
            resume_instruction=resume_instruction,
            spoken_so_far=text[-4000:],
            reason=reason,
        )

    # ---------------------------------------------------------- LLM refining

    def apply_llm_refinement(self, checkpoint: LessonCheckpoint, raw_json: str) -> LessonCheckpoint:
        """Merge a model-produced checkpoint JSON into the deterministic one."""
        data = _safe_json(raw_json)
        if not data:
            return checkpoint
        for key in ("topic", "section", "last_concept", "next_concept", "resume_instruction"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                setattr(checkpoint, key, value.strip())
        covered = data.get("concepts_covered")
        if isinstance(covered, list):
            for item in covered:
                if isinstance(item, str) and item.strip() and item not in checkpoint.concepts_covered:
                    checkpoint.concepts_covered.append(item.strip())
        return checkpoint


def _safe_json(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None
