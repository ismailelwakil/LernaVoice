"""Smart-resume prompts (§26, §28)."""

from __future__ import annotations

from typing import Any

from app.prompts.interaction import build_language_switch_prompt
from app.prompts.languages import resume_transition

RESUME_SYSTEM_SUFFIX = """RESUME MODE
You are returning to the lesson after an interruption.
- Open with a short natural transition, then continue with the NEXT concept.
- Do NOT restart the lesson. Do NOT re-explain concepts already covered.
- Do NOT summarise the question you just answered unless it is needed to bridge.
- One or two sentences of bridge, then teach."""


def build_resume_prompt(
    *,
    language: str,
    checkpoint: dict[str, Any] | None,
    answered_questions: list[str] | None = None,
    language_switch: bool = False,
) -> str:
    cp = checkpoint or {}
    covered = cp.get("concepts_covered") or []
    lines = [
        f"Resume the lesson. Begin with something equivalent to: \"{resume_transition(language)}\"",
        f"Topic: {cp.get('topic') or 'the current topic'}.",
        f"Section: {cp.get('section') or 'where we stopped'}.",
    ]
    if language_switch:
        # A mid-lesson switch must be heard: without this the student keeps hearing
        # the previous language until they happen to speak again.
        lines.insert(
            0,
            build_language_switch_prompt(
                language, section=str(cp.get("section") or ""), topic=str(cp.get("topic") or "")
            ),
        )
    if covered:
        lines.append("Already covered (do not repeat): " + ", ".join(str(c) for c in covered[:12]) + ".")
    if cp.get("last_concept"):
        lines.append(f"Last concept explained: {cp['last_concept']}.")
    if cp.get("next_concept"):
        lines.append(f"Continue with: {cp['next_concept']}.")
    if cp.get("resume_instruction"):
        lines.append(f"Instruction: {cp['resume_instruction']}")
    if answered_questions:
        lines.append("Questions already answered during the interruption: " + "; ".join(answered_questions[-3:]) + ".")
    return "\n".join(lines)


def build_recap_prompt(*, language: str, summary: str, checkpoint: dict[str, Any] | None, unresolved: list[str] | None = None) -> str:
    cp = checkpoint or {}
    lines = [
        "The student has returned to an earlier voice session.",
        f"Previous session summary: {summary or 'no summary recorded'}.",
        f"Checkpoint: topic={cp.get('topic')}, section={cp.get('section')}, "
        f"next concept={cp.get('next_concept')}.",
    ]
    if unresolved:
        lines.append("Still unanswered: " + "; ".join(unresolved[:3]) + ".")
    lines.append(
        "Give a two or three sentence spoken recap, then continue the lesson from the checkpoint. "
        "Do not restart."
    )
    return "\n".join(lines)
