"""Turn course material + vetted sources into an explanation a person would give.

The tutor does not read a syllabus out loud, and it does not improvise from
memory either. Given the topic the student picked, the student's level and the
trusted pack for that topic, this module builds the *brief* the tutor teaches
from:

    picture -> idea -> worked example -> why it holds -> the usual mistake -> check

That order is the "human logic" part: start where the student is, make the idea
concrete before it is precise, then justify it, then warn about the mistake
almost everyone makes, then ask something that proves it landed. The `moves` a
level gets come from `app/learning/levels.py` — a beginner is not given the same
explanation as an advanced student, only easier words about the same truth.

Two consumers:

  * the **live model** gets `prompt_block()` — the sourced facts plus the level's
    style sentence — and speaks it in the session language in its own words;
  * the **offline mock** gets the moves' own wording (`opening()`, `for_step()`)
    so the demo teaches the same grounded content with no vendor at all.

Everything is deterministic and offline: the same topic, level and language give
the same brief, which is what makes it testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.curriculum import Topic, resolve
from app.learning.levels import LevelStyle, normalise_level, style_for
from app.learning.sources import Item, Source, TopicPack, pack_for
from typing import Any

#: Lead-ins per move kind and language. Curated for the four languages whose demo
#: material is curated (en/ar/fr/sw); the rest fall back to English wording, which
#: is the same rule the lesson plan itself follows (see docs/EXPLANATION_ENGINE.md).
FRAMES: dict[str, dict[str, str]] = {
    "en": {
        "hook": "Let me put a picture in your head first.",
        "idea": "Here is the idea.",
        "fact": "One more thing you need.",
        "example": "Let us try it on something small.",
        "why": "And here is why that works.",
        "pitfall": "Watch out for this one.",
        "use": "That is why we reach for it when",
        "check": "Quick check:",
        "check_applied": "Your turn:",
        "check_open": "Think about this:",
        "summary": "So, to put it together:",
    },
    "ar": {
        "hook": "دعني أرسم لك صورة أولًا.",
        "idea": "الفكرة ببساطة:",
        "fact": "وهناك أمر آخر تحتاج إليه:",
        "example": "لنجرّبها على مثال صغير:",
        "why": "ولماذا يعمل هذا؟",
        "pitfall": "وانتبه إلى هذا الخطأ:",
        "use": "ولذلك نستخدمه عندما",
        "check": "سؤال سريع:",
        "check_applied": "دورك الآن:",
        "check_open": "فكّر في هذا:",
        "summary": "لنجمع الفكرة كلها:",
    },
    "fr": {
        "hook": "Je te donne d'abord une image.",
        "idea": "Voici l'idée.",
        "fact": "Encore un point nécessaire.",
        "example": "Essayons sur un petit exemple.",
        "why": "Et voici pourquoi cela marche.",
        "pitfall": "Attention à cette erreur.",
        "use": "C'est pour cela qu'on l'utilise quand",
        "check": "Petite vérification :",
        "check_applied": "À toi :",
        "check_open": "Réfléchis à ceci :",
        "summary": "Pour résumer :",
    },
    "sw": {
        "hook": "Nikupe picha kwanza.",
        "idea": "Wazo ni hili.",
        "fact": "Kuna jambo moja zaidi unalolithitaji.",
        "example": "Tujaribu kwa mfano mdogo.",
        "why": "Na kwa nini hii inafanya kazi?",
        "pitfall": "Jihadhari na kosa hili.",
        "use": "Ndiyo sababu tunaitumia wakati",
        "check": "Swali fupi:",
        "check_applied": "Zamu yako:",
        "check_open": "Fikiri kuhusu hili:",
        "summary": "Kwa muhtasari:",
    },
}

#: More than one way to lead into a move. Saying the same opener three times in
#: one lesson is exactly what makes a tutor sound like a template, so the lead-in
#: rotates per move (curated for English and Arabic; other languages keep the
#: single lead in FRAMES until someone translates the alternatives).
FRAME_VARIANTS: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "hook": ("Let me put a picture in your head first.", "Picture it like this.",
                 "Start somewhere familiar."),
        "idea": ("Here is the idea.", "The whole thing rests on one idea.",
                 "Let me give you the core of it.", "Start from this:", "The key is this:"),
        "fact": ("One more thing you need.", "Another piece of this.",
                 "And there is this to add.", "There is more to it:", "Keep this in view:"),
        "example": ("Let us try it on something small.", "Watch it on a tiny example.",
                    "Let us walk one case together."),
        "why": ("And here is why that works.", "Why does that hold?", "The reason is this."),
        "pitfall": ("Watch out for this one.", "This is where people slip.",
                    "Here is a trap to avoid."),
        "use": ("That is why we reach for it when", "You meet it whenever",
                "It earns its place when"),
    },
    "ar": {
        "hook": ("دعني أرسم لك صورة أولًا.", "تخيّل الموقف التالي.", "لنبدأ بصورة مألوفة."),
        "idea": ("الفكرة ببساطة:", "الأمر كله يقوم على فكرة واحدة:", "وخلاصة الفكرة:",
                 "لنبدأ من هنا:", "والمفتاح هو:"),
        "fact": ("وهناك أمر آخر تحتاج إليه:", "وثمّة نقطة ثانية:", "ويُضاف إلى ذلك:",
                 "وللأمر بقية:", "واحفظ هذا معك:"),
        "example": ("لنجرّبها على مثال صغير:", "شاهدها على مثال بسيط:", "لنمشِ على حالة واحدة معًا:"),
        "why": ("ولماذا يعمل هذا؟", "وما سبب صحته؟", "والسبب في ذلك:"),
        "pitfall": ("وانتبه إلى هذا الخطأ:", "هنا يقع كثيرون:", "ومن الأخطاء الشائعة:"),
        "use": ("ولذلك نستخدمه عندما", "وستقابله كلما", "ويكون الخيار الأول عندما"),
    },
}


def frame_lead(language: str, kind: str, index: int = 0) -> str:
    """A lead-in for this move, rotating so one lesson never repeats it.

    Once the alternatives for a kind are used up, a move is said with no lead-in
    at all rather than repeating an opener — which is also how a person talks
    when they are several points into an explanation.
    """
    variants = (FRAME_VARIANTS.get(language) or {}).get(kind)
    if variants:
        return variants[index] if 0 <= index < len(variants) else ""
    table = FRAMES.get(language) or FRAMES[FALLBACK_FRAME_LANGUAGE]
    if index != 0:
        return ""
    return table.get(kind) or FRAMES[FALLBACK_FRAME_LANGUAGE].get(kind, "")


FRAME_LANGUAGES: tuple[str, ...] = tuple(FRAMES)
FALLBACK_FRAME_LANGUAGE = "en"


@dataclass(frozen=True)
class Move:
    """One step of the explanation, with where its content came from."""

    kind: str
    text: str
    english: str
    sources: tuple[str, ...] = ()
    concepts: tuple[str, ...] = ()
    #: The lesson part this belongs to (1-based); 0 when the pack is unsectioned.
    section: int = 0

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "text": self.text,
            "english": self.english,
            "sources": list(self.sources),
            "concepts": list(self.concepts),
            "section": self.section,
        }


@dataclass(frozen=True)
class ExplanationBrief:
    topic_id: str
    topic: str
    level: str
    language: str
    style: LevelStyle
    moves: tuple[Move, ...]
    sources: tuple[Source, ...]
    #: Every vetted item of the pack in the lesson language, not just the slice this
    #: level teaches: a student's question is not limited to that slice, so answers
    #: come from the whole vetted pack rather than from nothing.
    answer_pool: tuple[tuple[str, str, str], ...] = ()
    plan: tuple[dict[str, str], ...] = ()
    #: "curated" when a vetted pack backs the topic, else "catalogue" (plan only).
    grounding: str = "curated"
    frames: str = FALLBACK_FRAME_LANGUAGE

    # ---------------------------------------------------------------- lookups
    def kinds(self) -> tuple[str, ...]:
        return tuple(m.kind for m in self.moves)

    def source_index(self) -> dict[str, Source]:
        return {s.id: s for s in self.sources}

    def check_move(self) -> Move | None:
        for move in reversed(self.moves):
            if move.kind == "check":
                return move
        return None

    def for_step(self, index: int) -> tuple[Move, ...]:
        """The moves that belong to lesson step `index` (they are spread in order)."""
        if not self.moves:
            return ()
        groups = _spread(self.moves, max(1, len(self.plan) or 1))
        return tuple(groups[min(max(index, 0), len(groups) - 1)])

    def opening(self, greeting: str, topic_line: str, student_name: str | None = None) -> str:
        """How the lesson starts: greet, name the topic, then the first moves."""
        who = f" {student_name}." if student_name else ""
        first = " ".join(m.text for m in self.for_step(0))
        return f"{greeting}{who} {topic_line} {first}".strip()

    # ----------------------------------------------------------------- shapes
    def as_dict(self) -> dict:
        return {
            "topic_id": self.topic_id,
            "topic": self.topic,
            "level": self.level,
            "language": self.language,
            "grounding": self.grounding,
            "frames": self.frames,
            "style": {"check": self.style.check, "clauses": self.style.max_clause_words},
            "moves": [m.as_dict() for m in self.moves],
            "sources": [s.as_dict() for s in self.sources],
            "source_names": [s.publisher for s in self.sources],
            "answer_pool": [
                {"kind": kind, "text": text, "english": english}
                for kind, text, english in self.answer_pool
            ],
        }

    def prompt_block(self) -> str:
        """What the live model is told, so the explanation stays grounded and easy.

        Empty when the topic has no vetted pack: an ungrounded topic is taught from
        the lesson plan alone, and the block exists to constrain what may be claimed.
        """
        if not self.moves:
            return ""
        lines = [
            "EXPLANATION PLAN (course material plus sources this service has vetted)",
            f"Topic: {self.topic} ({self.topic_id}). Student level: {self.level}.",
            self.style.instruction,
            "",
            "Teaching order that works for this student:",
            "  " + " -> ".join("picture" if k == "hook" else k for k in self.kinds()),
            "",
            "Sources you may rely on (cite by name if you mention one; never read a URL aloud):",
        ]
        for source in self.sources:
            lines.append(f"- {source.publisher}: {source.title} [{source.kind}]. {source.why}")
        lines += ["", "Facts you are allowed to teach — say them in your own words:"]
        for i, move in enumerate((m for m in self.moves if m.kind in ("idea", "fact", "why")), start=1):
            names = ", ".join(self.source_index()[sid].publisher for sid in move.sources if sid in self.source_index())
            lines.append(f"{i}. {move.english}" + (f"  (from {names})" if names else ""))
        for kind, label in (("hook", "Analogies"), ("example", "Worked example"),
                            ("pitfall", "Common mistake"), ("use", "When it is used")):
            entries = [m for m in self.moves if m.kind == kind]
            if entries:
                lines.append(f"{label}: " + " | ".join(m.english for m in entries))
        check = self.check_move()
        if check:
            lines.append(f"Closing question for this level: {check.english}")
        lines += [
            "",
            "How to teach it:",
            "- Explain in this order, in your own natural words, not by reciting this list.",
            "- Every factual claim must come from the facts above. If something is not covered,",
            "  say you would have to check the course material rather than guessing.",
            "- Match the student's level: sentence length, vocabulary and the kind of question you ask.",
            "- Keep it spoken: short sentences, no lists, no markdown, no URLs.",
        ]
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# building
# --------------------------------------------------------------------------- #


def _spread(items: tuple, groups: int) -> list[list]:
    """Spread `items` over `groups` in order, keeping the order they were built in."""
    if groups <= 1:
        return [list(items)]
    out: list[list] = [[] for _ in range(groups)]
    for index, item in enumerate(items):
        out[min(index, groups - 1)].append(item)
    return out


def _check_for(pack: TopicPack | None, style: LevelStyle, language: str) -> Item | None:
    if pack is None:
        return None
    checks = pack.of("check")
    if not checks:
        return None
    if style.check == "closed":
        chosen = checks[0]
    elif style.check == "applied":
        chosen = checks[1] if len(checks) > 1 else checks[0]
    else:
        chosen = checks[-1]
    return chosen


#: How many of each kind a level gets *per lesson part*. A section is taught
#: properly at every level: beginners get the picture and the plain idea, an
#: advanced student gets the reasoning, the edge cases and where it is used.
LEVEL_ITEMS: dict[str, dict[str, int]] = {
    "beginner": {"analogy": 1, "fact": 2, "example": 1, "pitfall": 1, "use": 0, "why": 0},
    "intermediate": {"analogy": 0, "fact": 3, "example": 1, "pitfall": 1, "use": 1, "why": 1},
    "advanced": {"analogy": 0, "fact": 3, "example": 1, "pitfall": 2, "use": 1, "why": 1},
}


def _select_sectioned(pack: "TopicPack", level: str) -> list[tuple[Item, str]]:
    """The items to teach, per lesson part, in the order a teacher would say them.

    Returns `(item, move_kind)` pairs: the first fact of a part is its *idea*, the
    analogy is the *picture*, and the rest keep their own kind.
    """
    budget = LEVEL_ITEMS.get(level, LEVEL_ITEMS["intermediate"])
    chosen: list[tuple[Item, str]] = []
    sections = sorted({i.section for i in pack.items if i.section})
    for section in sections:
        used: dict[str, int] = {}
        # "Here is the idea" introduces the whole lesson, not every part of it.
        first_fact = section == sections[0]
        for item in pack.items:
            if item.section != section or item.kind == "check":
                continue
            limit = budget.get(item.kind)
            if not limit or used.get(item.kind, 0) >= limit:
                continue
            used[item.kind] = used.get(item.kind, 0) + 1
            if item.kind == "analogy":
                kind = "hook"
            elif item.kind == "fact":
                kind = "idea" if first_fact else "fact"
                first_fact = False
            else:
                kind = item.kind
            chosen.append((item, kind))
    return chosen


def _item_move(item: Item, kind: str, sources: tuple[str, ...], language: str,
               frame_language: str, concepts: tuple[str, ...], section: int = 0,
               variant: int = 0) -> Move:
    lead = frame_lead(frame_language, kind, variant)
    return Move(
        kind=kind,
        text=f"{lead} {item.text(language)}".strip(),
        english=item.en,
        sources=sources,
        concepts=concepts,
        section=section or getattr(item, "section", 0),
    )


def _answer_pool(pack: "TopicPack", language: str) -> tuple[tuple[str, str, str], ...]:
    """Every teachable item of a pack, in the lesson language.

    Arabic only ever carries items that were actually translated, so an answer can
    never fall back to an English sentence in the middle of an Arabic lesson.
    """
    pool: list[tuple[str, str, str]] = []
    for item in pack.items:
        if item.kind == "check":
            continue
        text = item.text(language)
        if not text or (language == "ar" and not item.ar):
            continue
        pool.append((item.kind, text, item.en))
    return tuple(pool)


def build_brief(
    *,
    topic_id: str | None,
    topic_title: str | None = None,
    language: str = "en",
    level: str | None = None,
    plan: list[dict[str, str]] | None = None,
    evidence: list[Any] | None = None,
) -> ExplanationBrief:
    """The grounded, level-adapted teaching brief for one session's topic.

    `evidence` (round 26) lets a typed topic with no curated pack still get a real lesson:
    retrieved chunks of the student's *uploaded* material are composed into teaching moves.
    """
    level_key = normalise_level(level)
    style = style_for(level_key)
    language = language or "en"
    frame_language = language if language in FRAMES else FALLBACK_FRAME_LANGUAGE

    catalogue: Topic | None = resolve(topic_id, topic_title)
    title = (catalogue.title if catalogue else None) or topic_title or "this topic"
    steps = list(plan or (catalogue.lesson_plan() if catalogue else []))
    resolved_id = catalogue.id if catalogue else (topic_id or "")

    pack = pack_for(resolved_id)
    if pack is None:
        moves_from_upload: tuple[Move, ...] = ()
        if evidence:
            composed: list[Move] = []
            for i, chunk in enumerate(evidence):
                text = (getattr(chunk, "text", None) or (chunk.get("text") if isinstance(chunk, dict) else str(chunk))).strip()
                if not text:
                    continue
                src = getattr(chunk, "document_id", None) or (chunk.get("source") if isinstance(chunk, dict) else "uploaded")
                composed.append(Move(
                    kind="idea" if i % 2 == 0 else "fact",
                    text=text,
                    english=text,
                    sources=(src,) if src else (),
                    section=i + 1,
                ))
            moves_from_upload = tuple(composed)
        return ExplanationBrief(
            topic_id=resolved_id,
            topic=title,
            level=level_key,
            language=language,
            style=style,
            moves=moves_from_upload,
            sources=(),
            plan=tuple(steps),
            grounding="uploaded" if moves_from_upload else "catalogue",
            frames=frame_language,
        )

    source_ids = tuple(s.id for s in pack.sources)
    sectioned = any(getattr(i, "section", 0) for i in pack.items)
    concepts = tuple(catalogue.concepts[:4]) if catalogue and catalogue.concepts else (title,)

    facts = pack.of("fact")
    moves: list[Move] = []

    seen_kinds: dict[str, int] = {}

    def add(kind: str, item: Item | None, sources: tuple[str, ...] = source_ids) -> None:
        if item is None:
            return
        variant = seen_kinds.get(kind, 0)
        seen_kinds[kind] = variant + 1
        # No mixing languages inside one lesson. Arabic is spoken in fusHa only, so
        # an item the pack has not been translated for is left out rather than
        # dropped into the middle of an Arabic explanation as an English sentence
        # (8 of the 22 packs carry Arabic today). A topic left with no moves falls
        # back to the lesson plan alone, exactly like an uncurated topic.
        if language == "ar" and not item.ar:
            return
        moves.append(
            _item_move(item, kind, sources, language, frame_language, concepts, variant=variant)
        )

    if sectioned:
        # Teach the lesson part by part: every part gets its own idea, example and
        # trap for this level (see LEVEL_ITEMS), instead of a few facts spread thin.
        for item, kind in _select_sectioned(pack, level_key):
            add(kind, item)
        check = _check_for(pack, style, language)
        if check is not None:
            lead_key = {"closed": "check", "applied": "check_applied", "open": "check_open"}[style.check]
            lead = FRAMES[frame_language].get(lead_key, FRAMES["en"][lead_key])
            moves.append(
                Move(
                    kind="check",
                    text=f"{lead} {check.text(language)}".strip(),
                    english=check.en,
                    concepts=concepts,
                )
            )
        return ExplanationBrief(
            topic_id=resolved_id,
            topic=title,
            level=level_key,
            language=language,
            style=style,
            moves=tuple(moves),
            sources=pack.sources,
            answer_pool=_answer_pool(pack, language),
            plan=tuple(steps),
            grounding="curated",
            frames=frame_language,
        )

    if style.analogy:
        add("hook", pack.first("analogy"))
    add("idea", facts[0] if facts else None)
    if style.reasoning and len(facts) > 1:
        add("why", facts[1])
    if level_key == "advanced" and len(facts) > 2:
        add("fact", facts[2])
    add("example", pack.first("example"), source_ids)
    # Beginner and intermediate still need the remaining facts: teach them right
    # after the example, while the picture is still fresh.
    used = {m.english for m in moves}
    if level_key != "advanced":
        for extra in facts:
            if extra.en not in used:
                add("fact", extra)
                break
    for pitfall in pack.of("pitfall")[: style.pitfalls]:
        add("pitfall", pitfall)
    if "use" in style.moves:
        add("use", pack.first("use"))

    # The closing question is always the last thing spoken.
    check = _check_for(pack, style, language)
    if check is not None:
        lead_key = {"closed": "check", "applied": "check_applied", "open": "check_open"}[style.check]
        lead = FRAMES[frame_language].get(lead_key, FRAMES["en"][lead_key])
        moves.append(
            Move(
                kind="check",
                text=f"{lead} {check.text(language)}".strip(),
                english=check.en,
                sources=(),
                concepts=concepts,
            )
        )

    if not any(m.kind != "check" for m in moves):
        # The pack exists but had nothing to *teach* in this language — a lone
        # closing question is not an explanation.
        return ExplanationBrief(
            topic_id=resolved_id,
            topic=title,
            level=level_key,
            language=language,
            style=style,
            moves=(),
            sources=(),
            plan=tuple(steps),
            grounding="catalogue",
            frames=frame_language,
        )

    return ExplanationBrief(
        topic_id=resolved_id,
        topic=title,
        level=level_key,
        language=language,
        style=style,
        moves=tuple(moves),
        sources=pack.sources,
        answer_pool=_answer_pool(pack, language),
        plan=tuple(steps),
        grounding="curated",
        frames=frame_language,
    )
