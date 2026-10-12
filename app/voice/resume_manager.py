"""Smart resume coordinator (§26, §28)."""

from __future__ import annotations

from typing import Any

from app.voice.session_manager import VoiceSession
from app.voice.state import SessionState, VoiceSessionState


class ResumeManager:
    def __init__(self, session: VoiceSession):
        self.session = session

    @property
    def can_resume(self) -> bool:
        return self.session.state.state not in (SessionState.ENDED,) and (
            self.session.state.resume_checkpoint is not None
        )

    async def resume(self) -> dict[str, Any]:
        """Continue the lesson from the latest checkpoint without restarting."""
        if self.session.state.state is SessionState.ENDED:
            raise RuntimeError("session has ended")
        return await self.session.resume()

    @staticmethod
    def restore_plan(state: VoiceSessionState) -> dict[str, Any]:
        """What a returning student's session will do before any audio flows."""
        checkpoint = state.resume_checkpoint
        return {
            "session_id": state.session_id,
            "language": state.language,
            "topic": state.current_topic,
            "section": state.current_section,
            "summary": state.session_summary,
            "concepts_covered": state.concepts_covered,
            "unresolved_questions": state.unresolved_questions,
            "checkpoint": checkpoint.model_dump() if checkpoint else None,
            "next_action": state.next_action
            or (checkpoint.next_concept if checkpoint else "")
            or "continue_lesson",
            "will_recap": checkpoint is not None,
        }
