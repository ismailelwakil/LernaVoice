"""A small in-memory corpus for *uploaded* course material (round 26).

Standalone deployments have no LERNA content API, so a student's uploaded notes are
chunked and indexed here and retrieved by topic/question to build a grounded lesson.
Deliberately simple (token-overlap ranking) but real: ingestion, chunking, retrieval.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

_TOKEN = re.compile(r"[\w\u0600-\u06ff\u00c0-\u024f]+", re.UNICODE)
_STOP = {
    "the", "a", "an", "of", "in", "on", "is", "are", "and", "to", "that", "this", "for", "with",
    "من", "في", "على", "ان", "أن", "من", "هو", "هي", "التي", "الذي", "و", "او", "أو", "ثم",
}


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "") if t.lower() not in _STOP and len(t) > 2}


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    title: str
    text: str
    tokens: set[str] = field(default_factory=set)

    def score(self, query_tokens: set[str]) -> float:
        if not query_tokens:
            return 0.0
        overlap = len(self.tokens & query_tokens)
        return overlap / len(query_tokens)


_REGISTRY: dict[str, Chunk] = {}
_DOCUMENTS: dict[str, dict[str, Any]] = {}


def add_document(title: str, text: str, *, student_id: str | None = None, language: str | None = None) -> str:
    """Ingest uploaded material: split into sentence-ish chunks and index them."""
    document_id = "doc_" + uuid.uuid4().hex[:12]
    _DOCUMENTS[document_id] = {"title": title, "student_id": student_id, "language": language}
    sentences = [s.strip() for s in re.split(r"(?<=[.!?؟۔])\s+|\n+", text or "") if s.strip()]
    # group into chunks of ~2-3 sentences so each carries a usable idea
    for i in range(0, len(sentences), 2):
        body = " ".join(sentences[i:i + 2])
        if len(body) < 12:
            continue
        chunk = Chunk(
            chunk_id=f"{document_id}:{i}",
            document_id=document_id,
            title=title,
            text=body,
            tokens=_tokens(body),
        )
        _REGISTRY[chunk.chunk_id] = chunk
    return document_id


def document_count() -> int:
    return len(_DOCUMENTS)


def retrieve(
    query: str,
    *,
    document_ids: list[str] | None = None,
    top_k: int = 6,
) -> list[Chunk]:
    """Rank indexed chunks against `query` (token overlap), honouring document scope."""
    wanted = _tokens(query)
    pool = [c for c in _REGISTRY.values() if not document_ids or c.document_id in document_ids]
    scored = [(c.score(wanted), c) for c in pool]
    scored = [(s, c) for s, c in scored if s > 0]
    scored.sort(key=lambda sc: -sc[0])
    return [c for _, c in scored[:top_k]]


def reset() -> None:
    _REGISTRY.clear()
    _DOCUMENTS.clear()
