"""Demo dialogue policy: a mock tutor that holds up its end of a conversation.

The mock vendors return scripted audio, so without this they would monologue —
state a step, then state the next one regardless of what the student said. This
turns the lesson plan into an actual exchange: teach one step, ask whether it made
sense, and react to the answer (move on / rephrase / answer the question).

It is deliberately *demo* logic — the real behaviour is specified in
`app/prompts/interaction.py`, which is prepended to every real vendor's system
instruction. This is the offline stand-in for that, so the demo can be tested
without credentials.

Intent detection is keyword-based and multilingual on purpose: a student may
answer in the lesson language or slip into English, and both must work.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.curriculum import LOCALISED_GREETINGS
from app.learning.explainer import _spread
from app.curriculum_localisation import localise_sections, localise_topic
from app.voice.dialects import line_language
from app.learning.lesson_script import LessonScript, Pass, build_script
from app.prompts.interaction import (
    phrase,
    phrase_variants,
    move_on,
    react,
    speakable,
    step_lead,
    teach_frame,
)


class Intent(str, Enum):
    AFFIRM = "affirm"        # understood / yes / go on
    CONFUSED = "confused"    # no / I don't get it / repeat
    QUESTION = "question"    # an actual question was asked
    OTHER = "other"          # participation we cannot classify
    IMPOLITE = "impolite"    # rude / abusive — policy: warn once, then end
    UNCLEAR = "unclear"      # unintelligible — policy: repeat x3, then write, then give up


#: "yes, understood" — includes bare acknowledgements.
_AFFIRM = (
    "yes", "yeah", "yep", "ok", "okay", "okey", "sure", "got it", "i got it", "understood",
    "i understand", "clear", "makes sense", "correct", "right", "continue", "go on", "next",
    "نعم", "أيوه", "ايوه", "اه", "أه", "تمام", "فهمت", "أفهم", "أفهمها", "واضح", "صحيح", "ماشي", "طيب",
    "oui", "ouais", "d'accord", "compris", "je comprends", "clair", "continue", "ça marche",
    "ndiyo", "sawa", "nimeelewa", "naelewa", "sawa sawa", "endelea",
    "አዎ", "ገባኝ", "ግልጽ ነው", "እሺ", "ቀጥል",
    "eh", "iya", "na gane", "na fahimta", "to", "ci gaba",
    "haa", "waa fahmay", "waan fahmay", "sii wad",
    "bẹ́ẹ̀ ni", "mo ti yé mi", "ó yé mi", "tẹ̀síwájú",
    "ee", "m ghọtara", "ọ dị mma", "gaa n'ihu",
    "yebo", "ngiyaqonda", "ngizwa", "kulungile", "qhubeka",
)

#: "no / I don't understand" — checked before affirm ("i don't understand" contains "understand").
_CONFUSED = (
    "no", "nope", "not clear", "unclear", "confused", "i'm lost", "im lost", "lost me",
    "don't understand", "dont understand", "do not understand", "not understand",
    "didn't understand", "did not understand", "didn't get it", "not really", "not quite",
    "still lost", "i am lost", "i'm lost again", "not following", "not getting", "makes no sense",
    "doesn't make sense", "does not make sense", "confusing", "lost",
    "don't get it", "dont get it", "no idea", "idk", "i don't know", "i dont know",
    "repeat", "say again", "again please", "explain again", "hard", "difficult",
    "لا", "مش فاهم", "مش واضح", "ما فهمتش", "ما فهمت", "مو فاهم", "مش فاهمة", "لست فاهم", "صعب",
    "non", "pas clair", "je ne comprends pas", "je comprends pas", "perdu", "difficile",
    "hapana", "sielewi", "sijaelewa", "ngumu",
    "አይደለም", "አልገባኝም", "አልገባኝ", "አስቸጋሪ",
    "a'a", "ban gane ba", "ban fahimta ba", "mai wahala",
    "maya", "ma fahmin", "ma fahmin karo", "adag",
    "bẹ́ẹ̀ kọ́", "mi ò yé mi", "kò yé mi", "ó ṣòro",
    "mba", "aghọtaghị m", "ọ dịghị mfe",
    "cha", "angiqondi", "angizwa", "kunzima",
)

#: Question words per language — a bare question is not an affirmation.
_QUESTION_WORDS = (
    "what", "why", "how", "when", "where", "which", "who", "can you", "could you", "do you",
    "does it", "is it", "explain", "meaning",
    "ما", "لماذا", "ليه", "إزاي", "ازاي", "كيف", "هل", "متى", "أين", "فين", "اشرح",
    "quoi", "pourquoi", "comment", "est-ce que", "quand", "où",
    "nini", "kwa nini", "vipi", "lini", "wapi", "eleza",
    "ምን", "ለምን", "እንዴት", "መቼ", "የት", "አብራራ",
    "me", "menene", "yaushe", "ina", "yaya", "bayyana",
    "maxay", "waa maxay", "goorma", "xaggee", "sidee", "sharax",
    "kí ni", "kini", "ìdí", "báwo", "nígbà", "níbo", "ṣàlàyé",
    "gịnị", "kedu", "maka gịnị", "olee mgbe", "ebee", "kọwaa",
    "yini", "kanjani", "kungani", "nini", "kuphi", "chaza",
)


#: A trailing question mark is a question in every language this service speaks.
#: Arabic asks with "؟" (U+061F), Persian/Urdu with "؟" (U+06D4), Ethiopic with
#: "፧" (U+1367), Thai with "๛"/"?" — a student who types their own language's
#: question mark has asked a question, and must be answered, not waved through.
_QUESTION_MARKS = ("?", "؟", "؟", "؟", "፧", "？", "﹖")


#: Clearly rude/abusive tokens (Arabic + English). Deliberately narrow so a frustrated
#: "this is hard!" is never mistaken for abuse — policy warns once, then ends the lesson.
_IMPOLITE = (
    "غبي", "يا غبي", "حقير", "يا حقير", "كلب", "يا كلب", "حمار", "يا حمار", "تافه", "قذر",
    "وسخ", "يا وسخ", "اخرس", "اسكت يا", "وقح", "قليل الأدب", "قليل الادب", "زبالة",
    "stupid", "idiot", "dumb", "moron", "fool", "shut up", "you suck", "i hate you",
    "bastard", "asshole", "damn you", "useless", "rubbish", "you're trash",
)


def is_impolite(student_text: str) -> bool:
    padded = f" {(student_text or '').strip().lower()} "
    return any(_contains(padded, w) for w in _IMPOLITE)


def is_unclear(student_text: str) -> bool:
    """Heuristic for an unintelligible utterance (garbage STT / gibberish).

    A real sentence is mostly letters with a couple of words; noise is mostly
    symbols, a single stray character, or one short token with no sentence shape.
    """
    text = (student_text or "").strip()
    if not text:
        return False                       # silence is not "unclear", it is nothing
    padded = f" {text.lower()} "
    # A known short reply (نعم / yes / ok / "مش فاهم") is a real intent, not noise.
    if any(_contains(padded, w) for w in (_AFFIRM + _CONFUSED + _QUESTION_WORDS)):
        return False
    letters = sum(1 for ch in text if ch.isalpha())
    if letters / max(1, len(text)) < 0.5:
        return True                        # mostly punctuation / symbols / digits
    if len(text) <= 2:
        return True                        # a stray character
    if len(text.split()) == 1 and len(text) <= 6:
        return True                        # one short token, no sentence shape
    return False


def classify(student_text: str) -> Intent:
    """What the student just did: agree, object, ask, or just talk."""
    text = (student_text or "").strip().lower()
    if not text:
        return Intent.OTHER
    if is_impolite(text):
        return Intent.IMPOLITE
    # a question mark beats the "unclear" heuristic: "ทำไม?" is a question, not noise
    if any(mark in text for mark in _QUESTION_MARKS):
        return Intent.QUESTION
    if is_unclear(text):
        return Intent.UNCLEAR
    padded = f" {text} "
    if any(_contains(padded, w) for w in _CONFUSED):
        return Intent.CONFUSED
    if any(_contains(padded, w) for w in _AFFIRM):
        return Intent.AFFIRM
    if any(_contains(padded, w) for w in _QUESTION_WORDS):
        return Intent.QUESTION
    return Intent.OTHER


#: Small words that carry no meaning of their own when matching a question
#: against the material ("the", "and", "why", "what", and their Arabic forms).
_STOPWORDS = frozenset(
    """the a an of to in on for and or but is are was were do does did what why how when where
    which who can you it this that with from as be been we i my your his her their there here
    what's whats please explain tell me about difference between
    هل ما ماذا لماذا كيف متى أين الذي التي هذا هذه ذلك هلّا إيه إزاي ليه في من على عن إلى
    أن إن كان كانت هو هي نحن أنا أنت مع بين مثل غير كل بعض قد لا لم لن ثم أو و ف ب ل
    الفرق الفرقين عشان كده ده دي إيه""".split()
)


def _sentences_of(text: str) -> list[str]:
    """The sentences inside one grounded answer, whatever punctuation it uses."""
    import re

    return [part.strip() for part in re.split(r"(?<=[.!?\u061f])\s+", text) if part.strip()]


def _stems(text: str) -> set[str]:
    """Comparison stems: lowercased words with the common prefixes stripped off.

    Arabic and English both bury the meaningful part of a word behind prefixes
    ("البحث" / "the search"), so matching on stems is what lets "why do we split it
    in half?" find the sentence that talks about halving the range.
    """
    out: set[str] = set()
    for raw in (text or "").lower().replace("؟", " ").replace("،", " ").split():
        word = raw.strip(".,;:!?()[]\"'«»")
        if not word:
            continue
        for prefix in ("ال", "وال", "بال", "كال", "فال", "لل", "و", "ف", "ب", "ل", "ال"):
            if word.startswith(prefix) and len(word) - len(prefix) >= 3:
                word = word[len(prefix):]
                break
        if len(word) >= 3 and word not in _STOPWORDS:
            out.add(word)
    return out


def _relevance(question: str, move: dict) -> int:
    """How much of the student's question this grounded sentence actually answers."""
    asked = _stems(question)
    if not asked:
        return 0
    text = _stems(str(move.get("text") or "")) | _stems(str(move.get("english") or ""))
    return len(asked & text)


def _first_clause(sentence: str) -> str:
    """The opening clause of a sentence, ending like one — for a plainer re-run."""
    for mark in (": ", "؛ ", "; ", "، ", ", "):
        head, sep, _tail = sentence.partition(mark)
        if sep and len(head.split()) >= 4:
            head = head.strip().rstrip("،,;:")
            return head if head.endswith((".", "!", "?")) else head + "."
    return sentence


def _contains(padded_text: str, needle: str) -> bool:
    """Word-ish containment that still matches multi-word and non-Latin phrases.

    Latin phrases are matched on word boundaries so "no" does not fire inside
    "now"; languages without spaces (Amharic stems) fall back to substring.
    """
    if any("\u0600" <= ch <= "\u06ff" or "\u1200" <= ch <= "\u137f" for ch in needle):
        return needle in padded_text
    needle = needle.strip()
    if " " in needle:
        return needle in padded_text
    return f" {needle} " in padded_text or f" {needle}," in padded_text or f" {needle}." in padded_text


@dataclass
class TutorDialogue:
    """Walks a lesson plan the way a teacher would: one step, then a check-in."""

    language: str = "en"
    #: Which phrase table answers - today always the language itself. Arabic's
    #: table is the formal one; the hook stays so a second register can be added
    #: again without touching the dialogue.
    line_language: str = "en"
    sections: list[dict[str, str]] = field(default_factory=list)
    topic: str = "this topic"
    #: The catalogue's own name for the topic. The tutor *says* `topic`; the lesson
    #: position reported back to the service uses this, so checkpoints, resume and
    #: the plan lookup keep working whatever language the student switched to.
    plan_topic: str | None = None
    #: Catalogue id (`binary-search`) — used to store the English concept wording.
    topic_id: str | None = None
    student_name: str | None = None
    #: The grounded explanation brief (app/learning/explainer.py): the vetted
    #: facts, the level's teaching order and the closing question. Present for a
    #: catalogued topic; empty means "speak the plan wording as before".
    explanation: dict[str, Any] | None = None
    #: learner level this brief was built for (beginner | intermediate | advanced).
    level: str = "intermediate"
    step: int = 0
    #: Rotating cursor: which variant of a repeated line to use next.
    _variety: int = 0
    #: How many times the student has said they are lost (drives the explanation route).
    _explain_style: int = 0
    #: Last variant index used per key, so a line never repeats back-to-back.
    _used: dict[str, int] = field(default_factory=dict)
    #: True once the whole plan has been taught: further turns must not re-close it.
    done: bool = False
    #: The lesson as teaching passes (round 20). Present whenever the session was
    #: given a grounded brief; this is what makes a turn an explanation rather
    #: than a single line. `None` -> the older plan-reading behaviour.
    script: LessonScript | None = None
    #: Which pass of the script the tutor is teaching (and speaking) right now.
    pass_index: int = 0
    #: Rotates the grounded facts used to answer a question.
    _answered: int = 0
    #: Every grounded sentence already spoken, so an answer never repeats one.
    _spoken: set[str] = field(default_factory=set)
    #: True right after the tutor answered a question and asked "all clear?". The
    #: lesson is held at its current pass until the student confirms, then resumes
    #: from the part that follows (round 22: answer → confirm → continue).
    _awaiting_continue: bool = False
    #: Round 23: did the student ask anything during the lesson? If they stayed quiet
    #: the whole way, the tutor asks "any questions?" once at the very end instead of
    #: checking in after every part.
    _student_asked: bool = False
    #: Round 26 — conversation policy state.
    #: Consecutive unintelligible turns: 1-3 ask to repeat, 4th ask to type it,
    #: 5th+ admit "I didn't get your point".
    _unclear_count: int = 0
    #: Impolite turns: 1st warn, 2nd end the lesson.
    _impolite_count: int = 0
    #: True once the lesson was closed for conduct — nothing more is taught.
    _ended_for_conduct: bool = False

    # ---------------------------------------------------------------- helpers
    @classmethod
    def from_metadata(cls, metadata: dict[str, Any] | None, language: str) -> "TutorDialogue":
        md = metadata or {}
        sections = list(md.get("sections") or [])
        # The plan is written in English; the tutor speaks the student's language.
        # Curated translations cover the demo topics (app/curriculum_localisation.py);
        # anything else is spoken as written, which is the older behaviour.
        sections = localise_sections(language, md.get("topic_id"), sections)
        # A reconnected provider (failover, language change) is told which step the
        # lesson is on, so it carries on instead of starting the plan again (§21, §45).
        step = md.get("step_index")
        step = int(step) if isinstance(step, int) or (isinstance(step, str) and step.isdigit()) else 0
        step = max(0, min(step, len(sections) - 1)) if sections else 0
        dialogue = cls(
            language=language,
            line_language=line_language(language, md.get("dialect")),
            sections=sections,
            topic=localise_topic(language, md.get("topic_id"), md.get("topic_title"))
            or "this topic",
            plan_topic=md.get("topic_title") or None,
            topic_id=md.get("topic_id") or None,
            student_name=(md.get("student_name") or None),
            explanation=(md.get("explanation") or None),
            level=str(md.get("student_level") or "intermediate"),
            step=step,
        )
        dialogue.script = dialogue._build_script(sections)
        if dialogue.script and len(dialogue.script):
            # A reconnect (failover, language change) hands back `step_index`: carry
            # on from that pass instead of starting the explanation again (§21).
            dialogue.pass_index = max(0, min(step, len(dialogue.script) - 1))
        return dialogue

    # ------------------------------------------------------- teaching passes
    def _build_script(self, sections: list[dict[str, str]]) -> LessonScript | None:
        """The grounded brief as passes — the shape of a real explanation."""
        moves = (self.explanation or {}).get("moves") or []
        if not moves:
            return None
        style = (self.explanation or {}).get("style") or {}
        script = build_script(
            topic=self.topic,
            language=self.line_language,
            level=self.level,
            moves=moves,
            sections=sections,
            max_clause_words=int(style.get("clauses") or 24),
        )
        return script if len(script) else None

    @property
    def teaching(self) -> bool:
        """True when this tutor has a grounded lesson to teach, pass by pass."""
        return bool(self.script and len(self.script))

    def _pass_at(self, index: int) -> Pass | None:
        return self.script.at(index) if self.script else None

    def _speak_pass(self, index: int) -> str:
        """Speak one whole pass, and remember where the lesson now stands.

        `step` follows the pass's own plan section, so checkpoints and resume keep
        naming real lesson steps even though a turn now covers more ground.
        """
        current = self._pass_at(index)
        if current is None:
            return ""
        self.pass_index = index
        self.step = current.section_index
        # A sentence the student already heard (used to answer their question) is
        # not said a second time; the pass simply continues with the rest.
        pairs = list(zip(current.sentences, current.source_texts))
        fresh = [sentence for sentence, source in pairs if source not in self._spoken]
        self._spoken.update(source for _sentence, source in pairs)
        body = " ".join(fresh).strip()
        if not body:
            return ""                     # everything in this part is already said
        # Round 23: teach the part cleanly and move on — no comprehension question
        # after every part. The single "any questions?" comes once, at the very end
        # (`_after_lesson`), and only if the student never asked one themselves.
        return self._name(body)

    def _facts(self, count: int = 2, about: str = "", kinds: tuple[str, ...] = ()) -> str:
        """Grounded sentences to answer with — the pack's own words, never reused.

        A question is answered from the vetted material, preferring the parts of it
        the student has not heard yet, so the answer adds something instead of
        repeating the sentence they just questioned.
        """
        # The whole vetted pack, not just the slice this level teaches: a question
        # is not limited to that slice, and answering from nothing is worse than
        # answering from material the lesson had not reached yet.
        moves = [
            m
            for m in (self.explanation or {}).get("answer_pool")
            or (self.explanation or {}).get("moves")
            or []
            if m.get("kind") in (kinds or ("idea", "fact", "why", "example")) and m.get("text")
        ]
        if not moves:
            return ""
        if about:
            # A direct question outranks the no-repetition rule: if the material that
            # actually answers it was said a minute ago, it gets said again — without
            # its old lead-in, so it does not sound like a recording.
            scored = sorted(
                moves,
                key=lambda m: (-_relevance(about, m), str(m["text"]).strip() in self._spoken),
            )
            if _relevance(about, scored[0]) > 0:
                pool = scored
            else:
                pool = [m for m in moves if str(m["text"]).strip() not in self._spoken] or moves
        else:
            pool = [m for m in moves if str(m["text"]).strip() not in self._spoken] or moves
        if about:
            # A question is answered with the material that answers it — the rotation
            # cursor is for variety between unrelated turns, not for overriding fit.
            picked = pool[: min(count, len(pool))]
        else:
            picked = [pool[(self._answered + i) % len(pool)] for i in range(min(count, len(pool)))]
        self._answered += count
        said = []
        for move in picked:
            full = str(move["text"]).strip()
            text = self._drop_spoken_lead(full)
            self._spoken.add(full)
            self._spoken.add(text)
            # A beginner's pass re-cuts its sentences, so the same point can also be
            # sitting in `_spoken` in its shortened form — drop it rather than say it
            # twice in one session.
            pieces = _sentences_of(text)
            fresh = [piece for piece in pieces if piece not in self._spoken]
            if fresh and len(fresh) < len(pieces):
                # Part of this point was already said (a beginner's pass re-cuts its
                # sentences); keep only the part that is new.
                text = " ".join(fresh).strip()
                self._spoken.update(fresh)
            said.append(text)
        return " ".join(part for part in said if part)

    def _drop_spoken_lead(self, text: str) -> str:
        """Cut an opening the student has already heard off a grounded sentence.

        Answering with the pack's own wording is right; opening the answer with a
        lead-in the tutor used two minutes ago is what makes it sound canned.
        """
        head, sep, tail = text.partition(". ")
        if sep and head.strip().endswith((".", "!", "?", ":")) is False and head.strip() + "." in self._spoken:
            return tail.strip()
        head2, sep2, tail2 = text.partition(": ")
        if sep2 and head2.strip() + ":" in self._spoken:
            return tail2.strip()
        return text

    def _reteach(self, current: Pass) -> str:
        """Say the same part again by another route, never the same sentence twice."""
        self._explain_style += 1
        route = self._explain_style % 3
        # Prefer the parts of this section the student has not heard yet; only fall
        # back to re-cutting what they have.
        unheard = [s for s, src in zip(current.sentences, current.source_texts)
                   if src not in self._spoken]
        shorter = [_first_clause(s) for s in (unheard or current.sentences) if len(s.split()) > 8]
        self._spoken.update(current.source_texts)
        if route == 1:
            # Another way in, from the vetted pack: a picture or a worked example the
            # student has not heard yet. Re-cutting the same sentence is the last resort.
            other = self._facts(1, kinds=("analogy", "example"))
            if other:
                return self._name(
                    f"{self._v('rephrase')} {teach_frame(self.line_language, 'plainer')} "
                    f"{other} {self._v('encourage')}"
                )
        if route == 1 and shorter:
            return self._name(
                f"{self._v('rephrase')} {teach_frame(self.line_language, 'plainer')} "
                f"{' '.join(shorter[:3])} {self._v('encourage')}"
            )
        if route == 2:
            example = [s for s in current.sentences if teach_frame(self.line_language, "example") in s]
            if example:
                return self._name(f"{self._v('rephrase')} {example[0]} {self._v('encourage')}")
            return self._name(
                f"{self._v('rephrase')} {self._p('example')} "
                f"{self._t('which_part', title=self._title_lower({'title': current.section}))}"
            )
        return self._name(
            f"{self._v('rephrase')} {self._p('which_part')} "
            f"({current.section}) {self._v('encourage')}"
        )

    def _teach_turn(self, intent: Intent, student_text: str) -> str:
        """One teaching turn: re-explain, answer-and-continue, or teach the next pass."""
        current = self._pass_at(self.pass_index)
        if current is None:
            return self._name(self._generic(intent))

        # We just answered a question and asked "all clear?" — the lesson is parked
        # at `pass_index`. This turn picks up from there once the student responds.
        if self._awaiting_continue:
            self._awaiting_continue = False
            if intent is Intent.CONFUSED:
                return self._reteach(current)
            if intent is Intent.QUESTION:
                # Another question instead of a yes: answer it, ask again, stay put.
                return self._answer(student_text)
            # A yes (or anything not a question or a "lost"): carry on from the part
            # that follows the one we were on before the question interrupted.
            following = self.pass_index + 1
            if following >= len(self.script):
                return self._after_lesson(intent)
            ack = self._v("praise") if intent is Intent.AFFIRM else react(self.line_language, self._variety)
            return self._name(f"{ack} {self._speak_pass(following)}")

        if intent is Intent.CONFUSED:
            return self._reteach(current)

        if intent is Intent.QUESTION:
            return self._answer(student_text)

        following = self.pass_index + 1
        if following >= len(self.script):
            return self._after_lesson(intent)
        # An answer, a grunt, or a stray remark: acknowledge in a couple of words and
        # keep teaching. That is what a teacher does with the floor still theirs.
        if intent is Intent.AFFIRM:
            ack = self._v("praise")
        else:
            ack = react(self.line_language, self._variety)
        return self._name(f"{ack} {self._speak_pass(following)}")

    def _answer(self, question: str) -> str:
        """Answer from the vetted material, then carry on from where we were.

        The pack is scored against the student's own words, so the answer is the
        part of the material that actually bears on the question — and anything the
        student has already heard is left out, because repeating it is not an
        answer. Teaching then continues from the next part that still has something
        new in it.
        """
        answer = self._facts(2, about=question)
        parts = [self._p("answer_ack"), answer] if answer else [self._p("answer_ack")]
        # Round 22: answer, then ask "all clear?" in the lesson language and hold.
        # The lesson does not jump ahead on its own — the tutor waits for the student
        # to confirm, then resumes from the part right after the one just taught.
        parts.append(self._v("check"))
        self._awaiting_continue = True
        return self._name(" ".join(p for p in parts if p).strip())

    def _after_lesson(self, intent: Intent) -> str:
        """The plan is fully taught; keep being the student's teacher anyway.

        Finishing the sections does not end the conversation. A real teacher still
        answers what the student asks, still re-explains when they are stuck, and
        asks what they want next — they do not answer a question with "we're done".
        """
        current = self._pass_at(self.pass_index)
        if intent is Intent.CONFUSED and current is not None:
            return self._reteach(current)
        if intent is Intent.QUESTION:
            answer = self._facts(2)
            return self._name(f"{self._p('answer_ack')} {answer} {self._p('invite')}")
        # Winding up, but only the first time: after that the floor stays open.
        if self.done:
            praise = self._v("praise") if intent is Intent.AFFIRM else self._v("encourage")
            return self._name(f"{praise} {self._p('invite')}")
        self.done = True
        praise = (
            self._v("praise")
            if intent is Intent.AFFIRM
            else react(self.line_language, self._variety)
        )
        # Round 23: a student who never asked a single thing the whole lesson gets one
        # "any questions?" at the very end; a student who already asked just gets the
        # close (they know the floor is open).
        if not self._student_asked:
            return self._name(f"{praise} {self._p('invite')}")
        return self._name(f"{praise} {self._v('close')}")

    @property
    def planned(self) -> bool:
        return bool(self.sections)

    def current_section(self) -> dict[str, str] | None:
        if not self.planned:
            return None
        return self.sections[min(self.step, len(self.sections) - 1)]

    #: An English *phrase*: three or more Latin words in a row. A single technical
    #: term ("DNA", "ATP", "low") is fine inside an Arabic sentence; a whole English
    #: clause is the machine-switching-languages failure this scrubs out.
    _EN_PHRASE = re.compile(r"[A-Za-z][A-Za-z-']*(?: +[A-Za-z-']+){2,}")
    #: Only the languages written in a non-Latin script can be scrubbed by script:
    #: French, Swahili, Somali, Hausa, Yoruba and Zulu are themselves Latin-script,
    #: so a "three Latin words in a row" filter would strip their own teaching. For
    #: those the tutor simply never emits English — there is nothing safe to strip.
    _SCRUB_LANGUAGES = frozenset({"ar", "ar-eg", "am"})

    def _scrub(self, text: str) -> str:
        """Strip English phrases from a non-Latin-script utterance (Arabic, Amharic)."""
        if (self.line_language or "en") not in self._SCRUB_LANGUAGES:
            return text
        cleaned = self._EN_PHRASE.sub(" ", text)
        cleaned = " ".join(cleaned.split()).strip()
        return cleaned

    def _name(self, text: str) -> str:
        text = self._scrub(text)
        """Occasionally address the student by name — like a person would."""
        if not self.student_name:
            return text
        self._variety += 1
        if self._variety % 4 == 0:
            return f"{self.student_name}, {text[0].lower()}{text[1:]}"
        return text

    def _p(self, key: str) -> str:
        return phrase(self.line_language, key)

    def _v(self, key: str) -> str:
        """Another way of saying `key` — rotating, never the one just used.

        A tutor that answers every turn with the same sentence ("Does that make sense so
        far?") sounds like a prompt template. Each call walks the language's variants.
        """
        options = phrase_variants(self.line_language, key)
        if len(options) == 1:
            return options[0]
        last = self._used.get(key, -1)
        index = (last + 1) % len(options) if last >= 0 else self._variety % len(options)
        self._used[key] = index
        self._variety += 1
        return options[index]

    def _lead(self, section: dict[str, str], offset: int = 0) -> str:
        """One plan step as a spoken sentence, rotating the way it is introduced."""
        return step_lead(
            self.line_language,
            section.get("title", ""),
            section.get("goal", ""),
            index=self._variety + self.step + offset,
        )

    def _explained(self, index: int) -> str:
        """The grounded moves that belong to plan step `index`.

        The brief is split across the lesson's own sections, in the order the level
        asked for (picture -> idea -> example -> why -> mistake -> question), so the
        tutor teaches the vetted content instead of only describing the plan.
        """
        if not self.explanation:
            return ""
        moves = [m for m in (self.explanation.get("moves") or []) if m.get("text")]
        if not moves:
            return ""
        groups = _spread(moves, max(1, len(self.sections) or 1))
        spoken = [
            m["text"] for m in groups[min(max(index, 0), len(groups) - 1)]
            if m.get("kind") != "check"
        ]
        return " ".join(spoken).strip()

    def check_line(self) -> str:
        """This level's closing question from the brief, when there is one."""
        for move in (self.explanation or {}).get("moves") or []:
            if move.get("kind") == "check" and move.get("text"):
                return str(move["text"])
        return ""

    def _lead_or_explain(self, section: dict[str, str], index: int, offset: int = 0) -> str:
        """Prefer the grounded explanation; fall back to the plan's own wording."""
        return self._explained(index) or self._lead(section, offset)

    def _asking(self) -> bool:
        """Should this turn end with a question?

        Deliberately not every turn: explain, keep explaining, let the student break in.
        Roughly every second step gets a check, and one is always offered at the end.
        """
        return self.step % 2 == 1

    def _t(self, key: str, **parts: str) -> str:
        """A localised template with the step's own (English) course wording filled in."""
        template = phrase(self.line_language, key)
        try:
            return template.format(**parts)
        except (KeyError, IndexError):
            return template

    # ------------------------------------------------------------- utterances
    def opening(self) -> str:
        """Greet (in the lesson language), name the topic, teach step one."""
        greeting = (
            LOCALISED_GREETINGS.get(self.line_language)
            or LOCALISED_GREETINGS.get(self.language)
            or LOCALISED_GREETINGS["en"]
        )
        who = f" {self.student_name}." if self.student_name else ""
        if not self.planned:
            return f"{greeting}{who} {self._p('invite_stop')}"
        if self.teaching:
            # The first turn is already a taught part, developed properly — the pass
            # this session is on, which is pass one unless we are resuming.
            return f"{greeting}{who} {self._topic_line()} {self._speak_pass(self.pass_index)}"
        first = self.sections[0]
        # A person sets the scene before the first idea, then hands the turn over.
        return (
            f"{greeting}{who} {self._topic_line()} "
            f"{move_on(self.line_language, 0)} {self._lead_or_explain(first, 0)} "
            f"{self._p('invite_stop')}"
        )

    def _topic_line(self) -> str:
        return self._t("topic_line", topic=self.topic)

    def language_switch(self) -> str:
        """Confirm the switch in the new language and carry on from here."""
        if not self.planned:
            return self._name(f"{self._p('switch')} {self._p('invite_stop')}")
        if self.teaching:
            return self._name(f"{self._p('switch')} {self._speak_pass(self.pass_index)}")
        step = self.sections[min(self.step, len(self.sections) - 1)]
        tail = self.check_line() or (self._p("check") if self._asking() else self._p("invite_stop"))
        return self._name(
            f"{self._p('switch')} {self._lead_or_explain(step, self.step, offset=1)} {tail}"
        )

    def respond(self, student_text: str) -> str:
        """The tutor's next turn, driven by what the student actually said."""
        intent = classify(student_text)
        if intent is Intent.QUESTION:
            self._student_asked = True

        # ---- Round-26 conduct & comprehension policy (stateful, not scripted) ----
        if self._ended_for_conduct:
            return self._name(self._p("lesson_closed"))
        if intent is Intent.IMPOLITE:
            self._impolite_count += 1
            if self._impolite_count == 1:
                return self._name(self._p("polite_warn"))
            self._ended_for_conduct = True
            self.done = True
            return self._name(self._p("polite_end"))
        if intent is Intent.UNCLEAR:
            self._unclear_count += 1
            if self._unclear_count <= 3:
                return self._name(self._v("repeat_please"))
            if self._unclear_count == 4:
                return self._name(self._p("type_it"))
            self._unclear_count = 0
            return self._name(self._p("not_got"))
        self._unclear_count = 0            # a clear turn resets the streak

        if not self.planned:
            return self._name(self._generic(intent))

        if self.teaching:
            return self._teach_turn(intent, student_text)

        current = self.sections[min(self.step, len(self.sections) - 1)]

        if intent is Intent.CONFUSED:
            # Another route each time, and never the same words as the first attempt:
            # reworded content (speakable()), a different lead, a smaller step, or a
            # direct question about which part is fuzzy.
            self._explain_style += 1
            route = self._explain_style % 3
            plainer = speakable(self._simpler(current))
            if route == 1:
                return self._name(
                    f"{self._v('rephrase')} {self._p('simpler')} "
                    f"{self._t('put_simply', goal=plainer)} "
                    f"{self._v('encourage')}"
                )
            if route == 2:
                first_clause = self._goal(current).split(";")[0].split(",")[0].strip()
                if not first_clause.endswith((".", "!", "?")):
                    first_clause += "."
                return self._name(
                    f"{self._v('rephrase')} "
                    f"{self._t('smaller', goal=first_clause)} {self._v('encourage')}"
                )
            return self._name(
                f"{self._v('rephrase')} {self._p('example')} "
                f"{self._t('which_part', title=self._title_lower(current))}"
            )

        if intent is Intent.QUESTION:
            return self._name(
                f"{self._p('answer_ack')} "
                f"{self._t('on_current', title=self._title_lower(current), goal=self._goal(current))} "
                f"{self._p('invite')}"
            )

        if self.done:
            # The plan is finished; do not keep saying goodbye. Hand the floor back.
            return self._name(f"{self._v('praise')} {self._p('invite')}")

        if intent is Intent.AFFIRM:
            self.step += 1
            if self.step >= len(self.sections):
                self.done = True
                return self._name(f"{self._v('praise')} {self._v('close')}")
            step = self.sections[self.step]
            advance = self.step
            if self._asking():
                # Rotation order matters: praise, then the step, then the question —
                # the same order this tutor has always used, so the variety cursor
                # lands where the phrase tables expect it.
                praise = self._v("praise")
                lead = self._lead_or_explain(step, advance)
                tail = self.check_line() or self._v("check")
                return self._name(f"{praise} {lead} {tail}")
            # No question this turn: keep teaching and roll into the step after it, so
            # the lesson sounds like an explanation rather than an interrogation.
            line = f"{self._v('praise')} {self._lead_or_explain(step, advance)}"
            if self.step + 1 < len(self.sections):
                self.step += 1
                line += (
                    f" {self._p('going_on')} "
                    f"{self._lead_or_explain(self.sections[self.step], self.step, offset=2)}"
                )
            return self._name(line)

        # Plain participation ("mhm", "okay", a stray remark) — acknowledge and hold the
        # floor. Repeating the step verbatim would be the robotic thing to do.
        return self._name(f"{react(self.line_language, self._variety)} {self._p('holding')}")

    def _title_lower(self, section: dict[str, str]) -> str:
        title = section.get("title", "")
        return title[:1].lower() + title[1:] if title[:1].isupper() else title

    def _goal(self, section: dict[str, str]) -> str:
        goal = section.get("goal", "")
        return goal[:1].upper() + goal[1:] if goal[:1].islower() else goal

    def _simpler(self, section: dict[str, str]) -> str:
        goal = (section.get("goal") or "").rstrip(".")
        # a deliberately plainer restatement than the plan's own wording
        first_clause = goal.split(",")[0].strip() or goal
        # Arabic uses its own comma; an em dash here is read as a Latin pause and
        # looks like a machine switching typography mid-sentence.
        separator = "\u060c " if (self.language or "en") == "ar" else ", "
        return f"{first_clause}{separator}{self._p('nothing_more')}"

    def _generic(self, intent: Intent) -> str:
        if intent is Intent.CONFUSED:
            return f"{self._v('rephrase')} {self._v('encourage')}"
        if intent is Intent.QUESTION:
            return f"{self._p('answer_ack')} {self._p('invite')}"
        if intent is Intent.AFFIRM:
            return f"{self._v('praise')} {self._p('next')}"
        return f"{react(self.line_language, self._variety)} {self._p('going_on')}"
