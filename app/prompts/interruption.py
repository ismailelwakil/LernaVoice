"""Prompts covering the interrupt / question / follow-up cycle (§23-§25)."""

from __future__ import annotations

from typing import Any

from app.prompts.languages import interrupt_ack, language_name

INTERRUPT_SYSTEM_SUFFIX = """INTERRUPT MODE
The student just interrupted the lesson. You are no longer teaching; you are answering.
- Acknowledge in one short clause, then answer exactly what was asked.
- Stay anchored to the current lesson and the retrieved evidence.
- Expect follow-up questions. Keep the thread; do not restate the whole lesson.
- Do NOT resume the lesson until the service explicitly asks you to."""


def interrupt_acknowledgement(language: str) -> str:
    return interrupt_ack(language)


def build_question_prompt(
    *,
    question: str,
    language: str,
    checkpoint: dict[str, Any] | None,
    prior_questions: list[str] | None = None,
    is_followup: bool = False,
) -> str:
    lines = [
        f"The student asked (in {language_name(language)}): \"{question}\"",
    ]
    if is_followup and prior_questions:
        lines.append("This is a FOLLOW-UP. Earlier in this interruption they asked:")
        lines += [f"  - {q}" for q in prior_questions[-4:]]
    if checkpoint:
        lines.append(
            "Lesson position when they interrupted: "
            f"topic={checkpoint.get('topic')}, section={checkpoint.get('section')}, "
            f"last concept={checkpoint.get('last_concept')}."
        )
    lines.append(
        "Answer it directly and conversationally. Retrieve course evidence first if the "
        "question is factual. Do not resume the lesson yet."
    )
    return "\n".join(lines)


CHECKPOINT_EXTRACTION_PROMPT = """You are summarising a tutoring session into a learning checkpoint.
Return STRICT JSON only, no prose, with exactly these keys:
{
  "topic": string,
  "section": string,
  "concepts_covered": [string],
  "last_concept": string,
  "next_concept": string,
  "resume_instruction": string
}
`resume_instruction` must be one sentence telling a tutor exactly what to teach next.
Transcript of what the tutor has said so far:
---
{transcript}
---"""
