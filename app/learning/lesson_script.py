"""The teaching pass: what a teacher actually says in one turn.

A vetted brief (`app/learning/explainer.py`) is a list of *moves* — an idea, an
example, a trap, a closing question. Reading those moves out one per turn is not
teaching: it is a script being read ("one sentence, then: any questions?"). This
module turns the same grounded moves into **passes**: the part of the lesson being
taught, its ideas developed in order, the worked example, the trap, and the bridge
into what comes next — several sentences a teacher would say before pausing for
the student.

Nothing is invented. Every sentence is either

* a **grounded move** (the pack's own wording, already level-filtered and already
  in the lesson language by `build_brief`), or
* a **frame** from `app/prompts/interaction.py` — the connective tissue
  ("Picture it like this.", "This is where people slip.", "Once that is solid…").

The same structure is what the live model is told to do, so the offline tutor and
a real model teach the same lesson the same way.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.learning.explainer import _spread
from app.prompts.interaction import teach_frame


@dataclass(frozen=True)
class Pass:
    """One teaching turn: a developed part of the lesson, then (sometimes) a question."""

    index: int
    section_index: int
    section: str
    sentences: tuple[str, ...]
    question: str = ""
    #: Move kinds that went into this pass, in order — for tests and diagnostics.
    kinds: tuple[str, ...] = ()
    concepts: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    #: The same content in canonical English (never spoken; kept for the record).
    english: tuple[str, ...] = ()
    #: The grounded texts these sentences came from, so the tutor can tell which
    #: moves the student has already heard (and answer a question with the rest).
    source_texts: tuple[str, ...] = ()

    def text(self) -> str:
        """The whole pass, exactly as it is spoken."""
        return " ".join(self.sentences).strip()

    def script(self) -> str:
        """The pass plus its question, if this pass carries one."""
        return f"{self.text()} {self.question}".strip()

    def sentence_count(self) -> int:
        return len(self.sentences) + (1 if self.question else 0)

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "section_index": self.section_index,
            "section": self.section,
            "sentences": list(self.sentences),
            "question": self.question,
            "kinds": list(self.kinds),
            "concepts": list(self.concepts),
            "sources": list(self.sources),
            "source_texts": list(self.source_texts),
            "sentence_count": self.sentence_count(),
        }


@dataclass(frozen=True)
class LessonScript:
    """The whole lesson as teaching passes, in order."""

    topic: str
    language: str
    level: str
    passes: tuple[Pass, ...] = ()
    grounded: bool = True

    def __len__(self) -> int:
        return len(self.passes)

    def at(self, index: int) -> Pass | None:
        if not self.passes:
            return None
        return self.passes[max(0, min(index, len(self.passes) - 1))]

    def all_text(self) -> str:
        return " ".join(p.script() for p in self.passes)

    def as_dict(self) -> dict:
        return {
            "topic": self.topic,
            "language": self.language,
            "level": self.level,
            "grounded": self.grounded,
            "pass_count": len(self.passes),
            "passes": [p.as_dict() for p in self.passes],
        }


#: How often a pass is allowed to end with a question. A beginner is checked more
#: often because they have less to fall back on; an advanced student is left alone
#: to think. The last pass always closes with the level's own question.
ASK_EVERY: dict[str, int] = {"beginner": 2, "intermediate": 3, "advanced": 4}


def build_script(
    *,
    topic: str,
    language: str = "en",
    level: str = "intermediate",
    moves: tuple | list = (),
    sections: tuple | list = (),
    max_clause_words: int = 24,
) -> LessonScript:
    """Turn a brief's moves into the passes the tutor teaches from.

    `sections` is the lesson's own plan (title + goal); every pass is anchored to
    one of them, so a checkpoint still names a real lesson step.
    """
    content = [m for m in moves if _kind(m) != "check"]
    check = next((m for m in moves if _kind(m) == "check"), None)
    if not content:
        return LessonScript(topic=topic, language=language, level=level, passes=(), grounded=False)

    section_list = [dict(s) for s in sections] or [{"title": topic, "goal": ""}]
    groups = _group_by_section(content, len(section_list))
    ask_every = ASK_EVERY.get(level, 3)
    last = len(section_list) - 1

    passes: list[Pass] = []
    for index, section in enumerate(section_list):
        group = groups[index]
        if not group:
            continue
        pairs = _develop(group, language, level, max_clause_words)
        sentences = [sentence for sentence, _source in pairs]
        source_texts = [source for _sentence, source in pairs]
        next_title = ""
        if index < last:
            next_title = (section_list[index + 1].get("title") or "").strip()
            if next_title:
                bridge = f"{teach_frame(language, 'next')} {_lower_first(next_title)}."
                sentences.append(bridge)
                source_texts.append(bridge)
        asks = ((index + 1) % ask_every == 0) or index == last
        question = ""
        if asks and check is not None:
            question = _text(check)      # the move already leads with its own frame
        passes.append(
            Pass(
                index=index,
                section_index=index,
                section=(section.get("title") or "").strip() or topic,
                sentences=tuple(sentences),
                question=question,
                kinds=tuple(_kind(m) for m in group),
                concepts=tuple(_unique(c for m in group for c in _attr(m, "concepts"))),
                sources=tuple(_unique(s for m in group for s in _attr(m, "sources"))),
                english=tuple(_english(m) for m in group),
                source_texts=tuple(source_texts),
            )
        )
    return LessonScript(
        topic=topic, language=language, level=level, passes=tuple(passes), grounded=True
    )


# --------------------------------------------------------------------------- #
# internals
# --------------------------------------------------------------------------- #


def _group_by_section(moves: list, section_count: int) -> list[list]:
    """Put each move in the lesson part it belongs to.

    A sectioned pack already says which part each item teaches, so a pass covers
    that part and nothing else. An unsectioned pack (most of the catalogue for
    now) is spread evenly, which is the older behaviour.
    """
    if section_count and any(_section(m) for m in moves):
        buckets: list[list] = [[] for _ in range(section_count)]
        loose: list = []
        for move in moves:
            index = _section(move)
            if 1 <= index <= section_count:
                buckets[index - 1].append(move)
            else:
                loose.append(move)
        for position, move in enumerate(loose):          # untagged: fill the gaps
            buckets[position % section_count].append(move)
        return [bucket for bucket in buckets if bucket] or [list(moves)]
    return _spread(tuple(moves), section_count)


def _develop(group, language: str, level: str, max_clause_words: int) -> list[tuple[str, str]]:
    """The moves of one lesson part, as (sentence, the grounded text it came from).

    Each move already carries its own lead-in — `app/learning/explainer.py` picks
    one and rotates the alternatives per kind — so a pass adds nothing: it is the
    part's grounded sentences, in order, shortened for the level. Keeping the pair
    is what lets the tutor know a point has already been made, even after the
    sentence was re-cut for a beginner.
    """
    return [
        (_shorten(text, level, max_clause_words), text)
        for text in (_text(move) for move in group)
        if text
    ]


def _shorten(sentence: str, level: str, max_clause_words: int) -> str:
    """Beginners get the long clause broken in two, at its own punctuation.

    Nothing is rewritten or dropped: the sentence is split where the writer already
    put a pause, which is what makes it easier to follow when it is spoken.
    """
    limit = {"beginner": min(max_clause_words, 14), "intermediate": max_clause_words}.get(level, 24)
    words = sentence.split()
    if len(words) <= limit:
        return sentence
    for mark in (": ", "، ", " — ", ", ", "; "):
        head, sep, tail = sentence.partition(mark)
        if sep and len(head.split()) >= 4 and len(head.split()) < len(words) - 2:
            head = head.rstrip(" ،,")
            tail = tail.strip()
            if not tail:
                continue
            return f"{head}. {tail[:1].upper() + tail[1:]}"
    return sentence


def _kind(move) -> str:
    return str(getattr(move, "kind", "") or (move.get("kind") if isinstance(move, dict) else ""))


def _text(move) -> str:
    if isinstance(move, dict):
        return str(move.get("text") or "").strip()
    return str(getattr(move, "text", "") or "").strip()


def _english(move) -> str:
    if isinstance(move, dict):
        return str(move.get("english") or move.get("text") or "").strip()
    return str(getattr(move, "english", "") or getattr(move, "text", "") or "").strip()


def _attr(move, name: str) -> tuple:
    value = move.get(name) if isinstance(move, dict) else getattr(move, name, ())
    return tuple(value or ())


def _section(move) -> int:
    value = move.get("section") if isinstance(move, dict) else getattr(move, "section", 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _unique(items) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.append(item)
    return seen


def _lower_first(text: str) -> str:
    text = text.strip().rstrip(".")
    return text[:1].lower() + text[1:] if text[:1].isupper() else text
