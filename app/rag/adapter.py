"""RAG adapter (§29) — reuses LERNA's existing retrieval, never a new index."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import Settings, get_settings
from app.learning.sources import pack_for
from app.lerna_bridge import LernaBridge, LernaUnavailable, get_bridge
from app.logging_setup import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class EvidenceItem:
    chunk_id: str
    text: str
    source: str
    score: float = 0.0
    trust_score: float = 0.0
    source_type: str = "unknown"
    source_url: str | None = None
    page: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "source": self.source,
            "score": round(self.score, 4),
            "trust_score": round(self.trust_score, 4),
            "source_type": self.source_type,
            "source_url": self.source_url,
            "page": self.page,
        }


@dataclass(slots=True)
class RetrievalResult:
    query: str
    evidence: list[EvidenceItem] = field(default_factory=list)
    available: bool = True
    sufficient: bool = True
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "available": self.available,
            "sufficient": self.sufficient,
            "note": self.note,
            "evidence": [e.as_dict() for e in self.evidence],
        }

    def as_prompt_block(self, limit: int = 6) -> str:
        if not self.evidence:
            return (
                "No course evidence was retrieved for this question. Tell the student plainly "
                "that the course materials do not cover it, and answer only at the level you can "
                "support."
            )
        lines = ["Retrieved course evidence (cite it naturally, do not read IDs aloud):"]
        for i, item in enumerate(self.evidence[:limit], start=1):
            snippet = " ".join(item.text.split())[:600]
            lines.append(f"[{i}] ({item.source}, trust={item.trust_score:.2f}) {snippet}")
        if not self.sufficient:
            lines.append("Evidence is thin — acknowledge the uncertainty in one short sentence.")
        return "\n".join(lines)


class RAGAdapter:
    """Priority order: vetted sources -> current lesson -> LERNA course materials.

    The first tier is `app/learning/sources.py`: the sources this service chose
    and vetted for the topic. They answer even when LERNA's retrieval is
    unreachable, which is what lets the tutor stay grounded offline.
    """

    def __init__(self, bridge: LernaBridge | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.bridge = bridge or get_bridge(self.settings)

    def curated_evidence(self, topic_id: str | None) -> list[EvidenceItem]:
        """The topic's vetted facts, as retrieval evidence (~entitled to trust)."""
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
        """Vetted sources first, then whatever LERNA's own retrieval adds."""
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

    async def _retrieve_from_lerna(
        self,
        query: str,
        *,
        student_id: str,
        course_id: str | None = None,
        lesson_id: str | None = None,
        topic: str | None = None,
        document_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        k = top_k or self.settings.lerna_rag_top_k
        await self.bridge.ensure_ready()
        if not self.bridge.available:
            return RetrievalResult(
                query=query,
                available=False,
                sufficient=False,
                note="LERNA RAG is not reachable from the voice service",
            )
        try:
            if self.bridge.mode == "inprocess":
                return await self._retrieve_inprocess(
                    query, student_id=student_id, course_id=course_id, topic=topic or lesson_id,
                    document_ids=document_ids, k=k,
                )
            return await self._retrieve_http(
                query, student_id=student_id, course_id=course_id, document_ids=document_ids
            )
        except LernaUnavailable as exc:
            return RetrievalResult(query=query, available=False, sufficient=False, note=str(exc))
        except Exception as exc:
            log.warning("RAG retrieval failed", extra={"error_type": type(exc).__name__})
            return RetrievalResult(
                query=query, available=False, sufficient=False, note=f"retrieval error: {type(exc).__name__}"
            )

    async def _retrieve_inprocess(
        self,
        query: str,
        *,
        student_id: str,
        course_id: str | None,
        topic: str | None,
        document_ids: list[str] | None,
        k: int,
    ) -> RetrievalResult:
        import asyncio

        tutor = getattr(self.bridge.module, "tutor", None)
        retrieval = getattr(tutor, "retrieval", None) if tutor else None
        if retrieval is None:
            raise LernaUnavailable("LERNA retrieval service not exposed by the engine")

        raw = await asyncio.to_thread(
            retrieval.retrieve, query, student_id, document_ids, topic, k, course_id
        )
        items = _normalise_evidence(raw)
        return RetrievalResult(
            query=query,
            evidence=items,
            available=True,
            sufficient=bool(items) and max((i.score for i in items), default=0.0) > 0.0,
            note="" if items else "no matching course evidence",
        )

    async def _retrieve_http(
        self, query: str, *, student_id: str, course_id: str | None, document_ids: list[str] | None
    ) -> RetrievalResult:
        payload = {
            "student_id": student_id,
            "message": query,
            "course": course_id,
            "document_ids": document_ids,
        }
        data = await self.bridge.call_http(
            "POST", "/tutor/chat", json={k: v for k, v in payload.items() if v is not None},
            headers={"X-Student-Id": student_id},
        )
        items = _normalise_evidence(data.get("evidence") or [])
        return RetrievalResult(query=query, evidence=items, available=True, sufficient=bool(items))


def _normalise_evidence(raw: Any) -> list[EvidenceItem]:
    out: list[EvidenceItem] = []
    if not raw:
        return out
    sequence = raw if isinstance(raw, (list, tuple)) else getattr(raw, "evidence", []) or []
    for item in sequence:
        get = item.get if isinstance(item, dict) else lambda key, default=None: getattr(item, key, default)
        text = get("text", "") or ""
        if not text:
            continue
        out.append(
            EvidenceItem(
                chunk_id=str(get("chunk_id", "") or get("id", "") or f"chunk-{len(out)}"),
                text=text,
                source=str(get("source", "") or get("source_title", "") or "course material"),
                score=float(get("score", 0.0) or 0.0),
                trust_score=float(get("trust_score", 0.0) or 0.0),
                source_type=str(get("source_type", "unknown") or "unknown"),
                source_url=get("source_url", None),
                page=get("page", None),
            )
        )
    return out
