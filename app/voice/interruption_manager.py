"""Interruption coordinator (§23, §25).

The mechanics live on VoiceSession so that the WebSocket path and the REST path
cannot diverge. This module is the named entry point the rest of the service
and the tests use, and it enforces the cycle rules:

    speak -> interrupt -> question -> answer -> (follow-up -> answer)* -> resume

There is no limit on how many times the cycle may repeat.
"""

from __future__ import annotations

from typing import Any

from app.voice.session_manager import VoiceSession
from app.voice.state import SessionState


class InterruptionManager:
    def __init__(self, session: VoiceSession):
        self.session = session

    @property
    def active(self) -> bool:
        """True from the moment of an interrupt until the lesson is resumed."""
        return bool(self.session._in_question_mode) or self.session.state.state in (
            SessionState.INTERRUPTED,
            SessionState.ANSWERING,
        )

    @property
    def cycles(self) -> int:
        return self.session.state.interrupt_count

    async def interrupt(self, source: str = "student") -> dict[str, Any]:
        if self.session.state.state is SessionState.ENDED:
            raise RuntimeError("session has ended")
        return await self.session.interrupt(source=source)

    async def ask(self, text: str) -> dict[str, Any]:
        """Any question after the first one in the same interruption is a follow-up."""
        is_followup = self.active and any(q.answered for q in self.session.state.student_questions)
        record = await self.session.ask_question(text, is_followup=is_followup)
        return {
            "question_id": record.question_id,
            "is_followup": record.is_followup,
            "parent_question_id": record.parent_question_id,
        }

    def pending(self) -> list[str]:
        return [q.text for q in self.session.state.open_questions()]
