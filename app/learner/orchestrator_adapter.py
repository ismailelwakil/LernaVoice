"""Learning Orchestrator adapter (§31).

The Voice Tutor asks LERNA's existing orchestrator what to teach next; it never
computes a competing learning state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.lerna_bridge import LernaBridge, LernaUnavailable, get_bridge
from app.logging_setup import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class NextAction:
    action: str = "continue_lesson"
    concept: str | None = None
    reason: str = ""
    priority: str = "medium"
    available: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "concept": self.concept,
            "reason": self.reason,
            "priority": self.priority,
            "available": self.available,
        }


class OrchestratorAdapter:
    def __init__(self, bridge: LernaBridge | None = None):
        self.bridge = bridge or get_bridge()

    async def next_action(self, student_id: str) -> NextAction:
        await self.bridge.ensure_ready()
        if not self.bridge.available:
            return NextAction(available=False, reason="LERNA orchestrator unavailable")
        try:
            if self.bridge.mode == "inprocess":
                raw = await self.bridge.call_inprocess("get_next_learning_action", student_id)
            else:
                data = await self.bridge.call_http("GET", f"/students/{student_id}/learning")
                raw = (data or {}).get("next_best_action")
            return _to_action(raw)
        except LernaUnavailable as exc:
            return NextAction(available=False, reason=str(exc))
        except Exception as exc:
            log.warning("orchestrator lookup failed", extra={"error_type": type(exc).__name__})
            return NextAction(available=False, reason=type(exc).__name__)

    async def register_modality(self, student_id: str, session_id: str, lesson_id: str | None) -> None:
        """Announce that the voice modality is now active for this learner."""
        log.info(
            "voice modality active",
            extra={"student_id": student_id, "session_id": session_id, "lesson_id": lesson_id},
        )


def _to_action(raw: Any) -> NextAction:
    if raw is None:
        return NextAction(available=False, reason="no action returned")
    get = raw.get if isinstance(raw, dict) else lambda k, d=None: getattr(raw, k, d)
    return NextAction(
        action=str(get("action", None) or get("kind", None) or "continue_lesson"),
        concept=get("concept", None) or get("title", None),
        reason=str(get("reason", "") or ""),
        priority=str(get("priority", "medium") or "medium"),
        available=True,
    )
