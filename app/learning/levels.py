"""What the student can already handle — and how that changes the teaching.

The level lives in the student's LERNA Progress Profile. Until that integration
is switched on for this service, `app/learner/profiles.py` keeps a local copy so
the behaviour can be tested here; either way the tutor reads *one* number and
adapts the whole explanation to it:

  * beginner     — a familiar analogy first, short sentences, everyday example,
                   jargon avoided or explained where it appears, closed check.
  * intermediate — the idea, then a worked example, then why it holds; standard
                   terminology; complexity mentioned once; applied check.
  * advanced     — the idea and its justification, edge cases, limits and cost,
                   an open question instead of a yes/no check.

Nothing here is cosmetic: these knobs decide which moves the explanation is made
of, how long a spoken clause may be, and what the tutor asks at the end.
"""

from __future__ import annotations

from dataclasses import dataclass

BEGINNER = "beginner"
INTERMEDIATE = "intermediate"
ADVANCED = "advanced"
LEVELS: tuple[str, ...] = (BEGINNER, INTERMEDIATE, ADVANCED)
DEFAULT_LEVEL = INTERMEDIATE


@dataclass(frozen=True)
class LevelStyle:
    key: str
    label: str
    #: How the tutor is told to pitch it (one sentence, added to the instruction).
    instruction: str
    #: Spoken clauses longer than this are split before they reach the student.
    max_clause_words: int
    #: Which explanation moves this level is made of (see app/learning/explainer.py).
    moves: tuple[str, ...]
    #: How many common mistakes are worth raising.
    pitfalls: int
    #: Does an analogy open the explanation?
    analogy: bool
    #: Is "why it works / what it costs" part of the explanation?
    reasoning: bool
    #: The shape of the closing question.
    check: str  # "closed" | "applied" | "open"


STYLES: dict[str, LevelStyle] = {
    BEGINNER: LevelStyle(
        key=BEGINNER,
        label="Beginner",
        instruction=(
            "The student is a beginner: start from an everyday analogy, use short "
            "concrete sentences, avoid jargon or explain it the moment you use it, "
            "and keep to one idea at a time."
        ),
        max_clause_words=11,
        moves=("hook", "idea", "example", "pitfall", "check"),
        pitfalls=1,
        analogy=True,
        reasoning=False,
        check="closed",
    ),
    INTERMEDIATE: LevelStyle(
        key=INTERMEDIATE,
        label="Intermediate",
        instruction=(
            "The student is intermediate: give the idea, walk one worked example, then "
            "say why it works; use the standard terminology, and mention cost or limits "
            "once, briefly."
        ),
        max_clause_words=16,
        moves=("idea", "example", "why", "pitfall", "check"),
        pitfalls=1,
        analogy=False,
        reasoning=True,
        check="applied",
    ),
    ADVANCED: LevelStyle(
        key=ADVANCED,
        label="Advanced",
        instruction=(
            "The student is advanced: state the idea precisely, justify it, cover edge "
            "cases and the cost, and skip the analogy — they want the mechanism, not a "
            "story."
        ),
        max_clause_words=24,
        moves=("idea", "why", "example", "pitfall", "use", "check"),
        pitfalls=2,
        analogy=False,
        reasoning=True,
        check="open",
    ),
}

#: Spellings a profile might carry: "Beginner", "1", "A1", "first year", "مبتدئ".
_ALIASES: dict[str, str] = {
    "beginner": BEGINNER, "starter": BEGINNER, "novice": BEGINNER, "basic": BEGINNER,
    "easy": BEGINNER, "a1": BEGINNER, "a2": BEGINNER, "1": BEGINNER, "one": BEGINNER,
    "first year": BEGINNER, "first-year": BEGINNER, "freshman": BEGINNER,
    "grade 9": BEGINNER, "year 1": BEGINNER, "intro": BEGINNER, "introductory": BEGINNER,
    "مبتدئ": BEGINNER, "مبتدئه": BEGINNER, "مبتدئة": BEGINNER,
    "intermediate": INTERMEDIATE, "medium": INTERMEDIATE, "b1": INTERMEDIATE, "b2": INTERMEDIATE,
    "2": INTERMEDIATE, "two": INTERMEDIATE, "second year": INTERMEDIATE, "second-year": INTERMEDIATE,
    "sophomore": INTERMEDIATE, "undergraduate": INTERMEDIATE, "year 2": INTERMEDIATE,
    "متوسط": INTERMEDIATE, "متوسطه": INTERMEDIATE, "متوسطة": INTERMEDIATE,
    "advanced": ADVANCED, "expert": ADVANCED, "hard": ADVANCED, "c1": ADVANCED, "c2": ADVANCED,
    "3": ADVANCED, "three": ADVANCED, "third year": ADVANCED, "third-year": ADVANCED,
    "senior": ADVANCED, "year 3": ADVANCED, "year 4": ADVANCED, "graduate": ADVANCED,
    "متقدم": ADVANCED, "متقدمه": ADVANCED, "متقدمة": ADVANCED,
}


def normalise_level(value: str | int | None, default: str = DEFAULT_LEVEL) -> str:
    """Any spelling a profile might use -> one of the three levels."""
    if value is None:
        return default
    text = " ".join(str(value).strip().lower().replace("_", " ").split())
    text = text.replace("-", " ")
    return _ALIASES.get(text, _ALIASES.get(text.replace(" ", ""), default))


def style_for(level: str | int | None) -> LevelStyle:
    return STYLES[normalise_level(level)]


def is_known_level(value: str | int | None) -> bool:
    """True when the value names a level (as opposed to being an unknown word)."""
    if value is None:
        return False
    text = " ".join(str(value).strip().lower().replace("_", " ").split())
    return text in _ALIASES or text.replace("-", " ") in _ALIASES


def level_options() -> list[dict[str, str]]:
    """For GET /voice/languages-style discovery and the demo's level picker."""
    return [{"code": key, "label": STYLES[key].label} for key in LEVELS]
