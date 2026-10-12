"""Tool / function-calling surface exposed to the model (§29, §30, §32)."""

from __future__ import annotations

from typing import Any

TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "search_course_materials",
        "description": (
            "Retrieve evidence from the student's LERNA course materials, the current lesson and "
            "trusted LERNA sources. Call this before answering any factual question about the course."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look up, in English."},
                "topic": {"type": "string", "description": "Optional topic or lesson section to focus on."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "show_visual",
        "description": (
            "Display something on the student's screen while you keep speaking: code, an equation, "
            "a diagram description, or a table. Use it whenever the explanation is visual."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["code", "equation", "diagram", "table", "image", "text"],
                },
                "content": {"type": "string"},
                "language": {"type": "string", "description": "Programming language for code visuals."},
                "caption": {"type": "string"},
            },
            "required": ["type", "content"],
        },
    },
    {
        "name": "record_learning_signal",
        "description": (
            "Report an observation about the learner to the LERNA Progress Profile. Use it when a "
            "concept was discussed, understood or completed, when the student asks a question, or "
            "when you detect a misconception."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": [
                        "concept_discussed",
                        "concept_understood",
                        "question_asked",
                        "misconception_detected",
                        "concept_completed",
                        "needs_reinforcement",
                    ],
                },
                "concept": {"type": "string"},
                "detail": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["kind", "concept"],
        },
    },
    {
        "name": "update_lesson_position",
        "description": (
            "Tell the service where you are in the lesson so interruption checkpoints are accurate. "
            "Call it whenever you move to a new section or concept."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "section": {"type": "string"},
                "last_concept": {"type": "string"},
                "next_concept": {"type": "string"},
            },
            "required": ["section"],
        },
    },
]


def declarations_for(language: str) -> list[dict[str, Any]]:
    """Hook for per-language tool tweaks; identical for all ten today."""
    return TOOL_DECLARATIONS
