"""Round 19, part B: the mock teaches the brief, and RAG answers from it first.

Run once from the service root:  python3 tools/patch_explanation_engine_b.py
"""
import io


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub(path, pairs):
    s = read(path)
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    write(path, s)


# --------------------------------------------------------------------------- #
# 1. the offline tutor speaks the grounded, level-adapted moves
# --------------------------------------------------------------------------- #

sub("app/providers/mock/dialogue.py", [
    (
        """    student_name: str | None = None
    step: int = 0""",
        """    student_name: str | None = None
    #: The grounded explanation brief (app/learning/explainer.py): the vetted
    #: facts, the level's teaching order and the closing question. Present for a
    #: catalogued topic; empty means "speak the plan wording as before".
    explanation: dict[str, Any] | None = None
    #: learner level this brief was built for (beginner | intermediate | advanced).
    level: str = "intermediate"
    step: int = 0""",
    ),
    (
        """            student_name=(md.get("student_name") or None),
            step=step,
        )""",
        """            student_name=(md.get("student_name") or None),
            explanation=(md.get("explanation") or None),
            level=str(md.get("student_level") or "intermediate"),
            step=step,
        )""",
    ),
    (
        """    def _asking(self) -> bool:""",
        """    def _explained(self, index: int) -> str:
        \"\"\"The grounded moves that belong to plan step `index`.

        The brief is split across the lesson's own sections, in the order the level
        asked for (picture -> idea -> example -> why -> mistake -> question), so the
        tutor teaches the vetted content instead of only describing the plan.
        \"\"\"
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

    def _check_line(self) -> str:
        \"\"\"This level's closing question from the brief, when there is one.\"\"\"
        for move in (self.explanation or {}).get("moves") or []:
            if move.get("kind") == "check" and move.get("text"):
                return str(move["text"])
        return ""

    def _lead_or_explain(self, section: dict[str, str], index: int, offset: int = 0) -> str:
        \"\"\"Prefer the grounded explanation; fall back to the plan's own wording.\"\"\"
        return self._explained(index) or self._lead(section, offset)

    def _asking(self) -> bool:""",
    ),
    (
        """        first = self.sections[0]
        # A person sets the scene before the first idea, then hands the turn over.
        return (
            f"{greeting}{who} {self._topic_line()} "
            f"{move_on(self.line_language, 0)} {self._lead(first)} "
            f"{self._p('invite_stop')}"
        )""",
        """        first = self.sections[0]
        # A person sets the scene before the first idea, then hands the turn over.
        return (
            f"{greeting}{who} {self._topic_line()} "
            f"{move_on(self.line_language, 0)} {self._lead_or_explain(first, 0)} "
            f"{self._p('invite_stop')}"
        )""",
    ),
    (
        """        step = self.sections[min(self.step, len(self.sections) - 1)]
        tail = self._p("check") if self._asking() else self._p("invite_stop")
        return self._name(f"{self._p('switch')} {self._lead(step, offset=1)} {tail}")""",
        """        step = self.sections[min(self.step, len(self.sections) - 1)]
        tail = self._check_line() or (self._p("check") if self._asking() else self._p("invite_stop"))
        return self._name(
            f"{self._p('switch')} {self._lead_or_explain(step, self.step, offset=1)} {tail}"
        )""",
    ),
    (
        """            step = self.sections[self.step]
            if self._asking():
                return self._name(
                    f"{self._v('praise')} {self._lead(step)} {self._v('check')}"
                )
            # No question this turn: keep teaching and roll into the step after it, so
            # the lesson sounds like an explanation rather than an interrogation.
            line = f"{self._v('praise')} {self._lead(step)}"
            if self.step + 1 < len(self.sections):
                self.step += 1
                line += f" {self._p('going_on')} {self._lead(self.sections[self.step], offset=2)}"
            return self._name(line)""",
        """            step = self.sections[self.step]
            advance = self.step
            if self._asking():
                tail = self._check_line() or self._v("check")
                return self._name(
                    f"{self._v('praise')} {self._lead_or_explain(step, advance)} {tail}"
                )
            # No question this turn: keep teaching and roll into the step after it, so
            # the lesson sounds like an explanation rather than an interrogation.
            line = f"{self._v('praise')} {self._lead_or_explain(step, advance)}"
            if self.step + 1 < len(self.sections):
                self.step += 1
                line += (
                    f" {self._p('going_on')} "
                    f"{self._lead_or_explain(self.sections[self.step], self.step, offset=2)}"
                )
            return self._name(line)""",
    ),
])

# `_spread` lives in the explainer; the dialogue needs the same grouping rule.
sub("app/providers/mock/dialogue.py", [
    (
        "from app.curriculum import LOCALISED_GREETINGS",
        "from app.curriculum import LOCALISED_GREETINGS\nfrom app.learning.explainer import _spread",
    ),
])

# --------------------------------------------------------------------------- #
# 2. questions are answered from the vetted sources first
# --------------------------------------------------------------------------- #

sub("app/rag/adapter.py", [
    (
        """from app.config import Settings, get_settings
from app.lerna_bridge import LernaBridge, LernaUnavailable, get_bridge
from app.logging_setup import get_logger""",
        """from app.config import Settings, get_settings
from app.learning.sources import pack_for
from app.lerna_bridge import LernaBridge, LernaUnavailable, get_bridge
from app.logging_setup import get_logger""",
    ),
    (
        """class RAGAdapter:
    \"\"\"Priority order: current lesson -> course materials -> trusted LERNA sources.\"\"\"

    def __init__(self, bridge: LernaBridge | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.bridge = bridge or get_bridge(self.settings)

    async def retrieve(""",
        """class RAGAdapter:
    \"\"\"Priority order: vetted sources -> current lesson -> LERNA course materials.

    The first tier is `app/learning/sources.py`: the sources this service chose
    and vetted for the topic. They answer even when LERNA's retrieval is
    unreachable, which is what lets the tutor stay grounded offline.
    \"\"\"

    def __init__(self, bridge: LernaBridge | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.bridge = bridge or get_bridge(self.settings)

    def curated_evidence(self, topic_id: str | None) -> list[EvidenceItem]:
        \"\"\"The topic's vetted facts, as retrieval evidence (~entitled to trust).\"\"\"
        pack = pack_for(topic_id)
        if pack is None or not pack.sources:
            return []
        out: list[EvidenceItem] = []
        content = [i for i in pack.items if i.kind in ("fact", "example")]
        for index, item in enumerate(content):
            source = pack.sources[index % len(pack.sources)]
            out.append(
                EvidenceItem(
                    chunk_id=f"curated:{pack.topic_id}:{index}",
                    text=item.en,
                    source=f"{source.publisher} — {source.title}",
                    score=1.0,
                    trust_score=0.98,
                    source_type="curated",
                    source_url=source.url,
                )
            )
        return out

    async def retrieve(
        self,
        query: str,
        *,
        student_id: str,
        course_id: str | None = None,
        lesson_id: str | None = None,
        topic: str | None = None,
        topic_id: str | None = None,
        document_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        \"\"\"Vetted sources first, then whatever LERNA's own retrieval adds.\"\"\"
        curated = self.curated_evidence(topic_id)
        result = await self._retrieve_from_lerna(
            query,
            student_id=student_id,
            course_id=course_id,
            lesson_id=lesson_id,
            topic=topic,
            document_ids=document_ids,
            top_k=top_k,
        )
        if not curated:
            return result
        seen = {" ".join(e.text.split()).lower() for e in curated}
        merged = curated + [
            e for e in result.evidence if " ".join(e.text.split()).lower() not in seen
        ]
        return RetrievalResult(
            query=query,
            evidence=merged,
            available=True,
            sufficient=True,
            note=result.note or "answered from the vetted course sources",
        )

    async def _retrieve_from_lerna(""",
    ),
])

# --------------------------------------------------------------------------- #
# 3. the session passes the topic id and stops crying "RAG unavailable"
# --------------------------------------------------------------------------- #

sub("app/voice/session_manager.py", [
    (
        """            lesson_id=self.state.lesson_id,
            topic=self.state.current_topic,
            document_ids=self.state.document_ids,
        )""",
        """            lesson_id=self.state.lesson_id,
            topic=self.state.current_topic,
            topic_id=self.state.topic_id,
            document_ids=self.state.document_ids,
        )""",
    ),
    (
        """        if not result.available:
            await self.emit(
                error_event(
                    ErrorCode.VOICE_RAG_UNAVAILABLE,
                    "Course materials could not be searched; answering from lesson context only.",
                    recoverable=True,
                    session_id=self.state.session_id,
                )
            )""",
        """        if not result.available and not result.evidence:
            await self.emit(
                error_event(
                    ErrorCode.VOICE_RAG_UNAVAILABLE,
                    "Course materials could not be searched; answering from the lesson's "
                    "vetted sources only.",
                    recoverable=True,
                    session_id=self.state.session_id,
                )
            )""",
    ),
    (
        """                # The offline mock teaches the same grounded brief, level and all.
                "explanation_moves": [m.as_dict() for m in brief.for_step(0)],
                "explanation": brief.as_dict(),""",
        """                # The offline mock teaches the same grounded brief, level and all.
                "explanation": brief.as_dict(),""",
    ),
])
print("part B: grounded mock dialogue + vetted-source-first retrieval")
