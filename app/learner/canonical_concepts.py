"""Learning state is English; only the teaching is multilingual.

Whatever language the tutor *speaks*, the concepts it **saves** must be the
catalogue's own English wording \u2014 otherwise the Progress Profile, the checkpoints
and the resume instructions fill up with Arabic/French/Swahili strings that no
downstream LERNA component can match against the curriculum.

Two things make this possible without an LLM:

1. the catalogue is already English (`app/curriculum.py`, sections carry their own
   `concepts`);
2. any localised wording we speak comes from a curated table
   (`app/curriculum_localisation.py`), so the reverse mapping is known.

`canonicalise_concept()` therefore resolves, in order:

  * English text \u2192 stored as said, with `catalogue_ref` set to the curriculum
    phrase it clearly matches (never rewriting the tutor's own English wording);
  * a localised title/goal, or a fragment of one \u2192 that section's English concept;
  * anything else non-English \u2192 kept as spoken and flagged `resolved=False`, with
    the language recorded, so nothing is silently invented or lost.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.curriculum import resolve
from app.curriculum_localisation import LOCALISED_STEPS

_WORDS = re.compile(r"[\w\u0600-\u06ff\u1200-\u137f]+", re.UNICODE)

#: Dropped before comparing English paraphrases: "the idea of halving" and
#: "we keep halving the range" share exactly one meaningful word.
_STOPWORDS = {
    "the", "a", "an", "of", "on", "in", "to", "it", "is", "are", "and", "or", "for",
    "with", "that", "this", "we", "you", "as", "at", "by", "from", "be", "its",
}

#: Overlap needed before a paraphrase is mapped onto a catalogue concept.
_MIN_OVERLAP = 0.5


@dataclass(frozen=True)
class Concept:
    """What to store (`canonical`) and what was actually said (`spoken`).

    `catalogue_ref` is the curriculum's own English phrase this concept maps onto,
    when one matches — an anchor for downstream matching that never overwrites
    wording the tutor chose to use in English.
    """

    canonical: str
    spoken: str
    language: str
    resolved: bool
    topic_id: str | None = None
    catalogue_ref: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "concept": self.canonical,
            "spoken_as": self.spoken if self.spoken != self.canonical else None,
            "catalogue_ref": self.catalogue_ref,
            "language": self.language,
        }


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").strip().lower()
    text = re.sub(r"[.!?…،؛:؛]+$", "", text).strip()
    return " ".join(text.split())


def _tokens(text: str) -> set[str]:
    return {t for t in (w.lower() for w in _WORDS.findall(text or "")) if len(t) > 2}


def _content_tokens(text: str) -> set[str]:
    return {t for t in _tokens(text) if t not in _STOPWORDS}


def _ascii_english(text: str) -> bool:
    """True when the text is (already) written in the catalogue's script."""
    letters = [ch for ch in text if ch.isalpha()]
    return bool(letters) and all(ch.isascii() for ch in letters)


def _section_concepts(topic_id: str) -> dict[str, str]:
    """English title/goal \u2192 the canonical concept phrase for that section."""
    topic = resolve(topic_id)
    if topic is None:
        return {}
    out: dict[str, str] = {"__topic__": topic.title}
    for section in topic.sections:
        phrase = section.concepts[0] if getattr(section, "concepts", None) else section.title
        out[_norm(section.title)] = phrase
        out[_norm(section.goal)] = phrase
    return out


def _reverse_index(topic_id: str | None, language: str) -> dict[str, tuple[str, str | None]]:
    """localised text \u2192 (English concept, topic id) for the curated languages."""
    index: dict[str, tuple[str, str | None]] = {}
    languages = [language] if language in LOCALISED_STEPS else list(LOCALISED_STEPS)
    for lang in languages:
        for key, steps in LOCALISED_STEPS[lang].items():
            if topic_id and key != topic_id:
                continue
            topic = resolve(key)
            if topic is None:
                continue
            by_title = {_norm(s.title): s for s in topic.sections}
            for english_title, (local_title, local_goal) in steps.items():
                section = by_title.get(_norm(english_title))
                phrase = (
                    section.concepts[0]
                    if section is not None and getattr(section, "concepts", None)
                    else english_title
                )
                index[_norm(local_title)] = (phrase, key)
                index[_norm(local_goal)] = (phrase, key)
    return index


def _best_concept_for_topic(topic_id: str | None, spoken: str) -> str | None:
    """Nearest catalogue concept by token overlap, when the match is convincing."""
    if not topic_id or not _ascii_english(spoken):
        return None
    spoken_tokens = _tokens(spoken)
    spoken_content = _content_tokens(spoken)
    if not spoken_tokens:
        return None
    best: tuple[float, str] | None = None
    for phrase, concept in _section_concepts(topic_id).items():
        if phrase.startswith("__"):
            continue
        concept_content = _content_tokens(phrase)
        if not concept_content:
            continue
        # how much of the *concept* the sentence actually voices
        score = len(concept_content & spoken_content) / len(concept_content)
        if best is None or score > best[0]:
            best = (score, concept)
    if best and best[0] >= _MIN_OVERLAP:
        return best[1]
    return None


def canonicalise_concept(
    text: str, *, language: str = "en", topic_id: str | None = None
) -> Concept:
    """The English concept to store for something the tutor said in `language`."""
    language = (language or "en").lower()
    spoken = " ".join((text or "").split())
    if not spoken:
        return Concept("", "", language, resolved=True, topic_id=topic_id)

    # Already English: store it as it stands — the words are the tutor's, and the
    # catalogue anchor (when one matches) rides along instead of replacing them.
    if _ascii_english(spoken):
        return Concept(
            spoken,
            spoken,
            language,
            resolved=True,
            topic_id=topic_id,
            catalogue_ref=_best_concept_for_topic(topic_id, spoken),
        )

    index = _reverse_index(topic_id, language)
    normalised = _norm(spoken)
    if normalised in index:
        concept, key = index[normalised]
        return Concept(concept, spoken, language, resolved=True, topic_id=key or topic_id,
                       catalogue_ref=concept)

    # A longer sentence or a fragment of one (a paraphrase, or a checkpoint taken
    # mid-sentence): map it onto the localised phrase it overwhelmingly comes from.
    spoken_tokens = _tokens(spoken)
    best: tuple[float, str, str | None] | None = None
    for localised, (concept, key) in index.items():
        localised_tokens = _tokens(localised)
        if not localised_tokens:
            continue
        shared = spoken_tokens & localised_tokens
        if len(shared) < 2:
            continue
        # measured against the shorter side, so a fragment of a phrase still matches
        coverage = len(shared) / min(len(spoken_tokens), len(localised_tokens))
        if coverage >= 0.66 and (best is None or coverage > best[0]):
            best = (coverage, concept, key)
    if best is not None:
        return Concept(best[1], spoken, language, resolved=True, topic_id=best[2] or topic_id,
                       catalogue_ref=best[1])

    # English text that paraphrases a known section (the live model does this).
    guess = _best_concept_for_topic(topic_id, spoken)
    if guess:
        return Concept(guess, spoken, language, resolved=True, topic_id=topic_id, catalogue_ref=guess)

    # Unknown wording: keep it, flag it, and record which language it came in, so the
    # profile can still be reconciled later rather than guessing a translation.
    return Concept(spoken, spoken, language, resolved=False, topic_id=topic_id)


def canonical_topic(topic_id: str | None, title: str) -> str:
    """The catalogue's title for a topic, whichever language named it."""
    topic = resolve(topic_id) if topic_id else None
    if topic is not None:
        return topic.title
    if _ascii_english(title):
        return title
    for key, steps in LOCALISED_STEPS.get("ar", {}).items():
        if title.strip() and title.strip() in steps.values():
            topic = resolve(key)
            if topic is not None:
                return topic.title
    return title


def catalogue_concepts(topic_id: str | None) -> list[str]:
    """The English concept phrases of a topic, in plan order."""
    topic = resolve(topic_id) if topic_id else None
    if topic is None:
        return []
    out = []
    for section in topic.sections:
        concepts = getattr(section, "concepts", None) or [section.title]
        out.append(concepts[0])
    return out


__all__ = ["Concept", "canonicalise_concept", "canonical_topic", "catalogue_concepts"]
