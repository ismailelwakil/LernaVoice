"""Voice persistence: abstract repository + in-memory and MongoDB backends."""

from __future__ import annotations

import asyncio
import copy
from abc import ABC, abstractmethod
from typing import Any

from app.config import Settings, get_settings
from app.logging_setup import get_logger
from app.persistence.models import (
    CHECKPOINTS,
    INTERACTIONS,
    PROVIDER_EVENTS,
    QUESTIONS,
    SESSIONS,
    CheckpointDoc,
    InteractionDoc,
    ProviderEventDoc,
    QuestionDoc,
    document_to_session,
    session_to_document,
)
from app.voice.state import VoiceSessionState

log = get_logger(__name__)


class VoiceRepository(ABC):
    backend: str = "abstract"

    @abstractmethod
    async def save_session(self, state: VoiceSessionState) -> None: ...

    @abstractmethod
    async def get_session(self, session_id: str) -> VoiceSessionState | None: ...

    @abstractmethod
    async def latest_session_for_student(
        self, student_id: str, *, course_id: str | None = None, lesson_id: str | None = None
    ) -> VoiceSessionState | None: ...

    @abstractmethod
    async def list_sessions(self, student_id: str, limit: int = 20) -> list[VoiceSessionState]: ...

    @abstractmethod
    async def append_checkpoint(self, doc: CheckpointDoc) -> None: ...

    @abstractmethod
    async def append_interaction(self, doc: InteractionDoc) -> None: ...

    @abstractmethod
    async def upsert_question(self, doc: QuestionDoc) -> None: ...

    @abstractmethod
    async def append_provider_event(self, doc: ProviderEventDoc) -> None: ...

    @abstractmethod
    async def history(self, session_id: str) -> dict[str, list[dict[str, Any]]]: ...

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


# --------------------------------------------------------------------------- #
# in-memory (tests, local dev without Mongo)
# --------------------------------------------------------------------------- #


class InMemoryVoiceRepository(VoiceRepository):
    backend = "memory"

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._collections: dict[str, list[dict[str, Any]]] = {
            CHECKPOINTS: [],
            INTERACTIONS: [],
            QUESTIONS: [],
            PROVIDER_EVENTS: [],
        }
        self._lock = asyncio.Lock()

    async def save_session(self, state: VoiceSessionState) -> None:
        async with self._lock:
            self._sessions[state.session_id] = copy.deepcopy(session_to_document(state))

    async def get_session(self, session_id: str) -> VoiceSessionState | None:
        doc = self._sessions.get(session_id)
        return document_to_session(copy.deepcopy(doc)) if doc else None

    async def latest_session_for_student(
        self, student_id: str, *, course_id: str | None = None, lesson_id: str | None = None
    ) -> VoiceSessionState | None:
        matches = [
            d
            for d in self._sessions.values()
            if d.get("student_id") == student_id
            and (course_id is None or d.get("course_id") == course_id)
            and (lesson_id is None or d.get("lesson_id") == lesson_id)
        ]
        if not matches:
            return None
        latest = max(matches, key=lambda d: d.get("updated_at", 0))
        return document_to_session(copy.deepcopy(latest))

    async def list_sessions(self, student_id: str, limit: int = 20) -> list[VoiceSessionState]:
        matches = [d for d in self._sessions.values() if d.get("student_id") == student_id]
        matches.sort(key=lambda d: d.get("updated_at", 0), reverse=True)
        return [document_to_session(copy.deepcopy(d)) for d in matches[:limit]]

    async def append_checkpoint(self, doc: CheckpointDoc) -> None:
        self._collections[CHECKPOINTS].append(doc.model_dump())

    async def append_interaction(self, doc: InteractionDoc) -> None:
        self._collections[INTERACTIONS].append(doc.model_dump())

    async def upsert_question(self, doc: QuestionDoc) -> None:
        bucket = self._collections[QUESTIONS]
        for i, existing in enumerate(bucket):
            if existing["question_id"] == doc.question_id:
                bucket[i] = doc.model_dump()
                return
        bucket.append(doc.model_dump())

    async def append_provider_event(self, doc: ProviderEventDoc) -> None:
        self._collections[PROVIDER_EVENTS].append(doc.model_dump())

    async def history(self, session_id: str) -> dict[str, list[dict[str, Any]]]:
        return {
            name: [copy.deepcopy(d) for d in docs if d.get("session_id") == session_id]
            for name, docs in self._collections.items()
        }


# --------------------------------------------------------------------------- #
# MongoDB
# --------------------------------------------------------------------------- #


class MongoVoiceRepository(VoiceRepository):
    backend = "mongo"

    def __init__(self, uri: str, db_name: str):
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("motor is required for the MongoDB backend: pip install motor") from exc
        self._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000, uuidRepresentation="standard")
        self._db = self._client[db_name]
        self._indexes_ready = False

    async def _ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        try:
            await self._db[SESSIONS].create_index([("student_id", 1), ("updated_at", -1)])
            await self._db[SESSIONS].create_index([("student_id", 1), ("course_id", 1), ("lesson_id", 1)])
            for coll in (CHECKPOINTS, INTERACTIONS, QUESTIONS, PROVIDER_EVENTS):
                await self._db[coll].create_index([("session_id", 1), ("timestamp", -1)], name="session_ts")
            self._indexes_ready = True
        except Exception as exc:  # pragma: no cover - index creation is best effort
            log.warning("mongo index creation failed", extra={"error_type": type(exc).__name__})

    async def save_session(self, state: VoiceSessionState) -> None:
        await self._ensure_indexes()
        doc = session_to_document(state)
        await self._db[SESSIONS].replace_one({"_id": state.session_id}, doc, upsert=True)

    async def get_session(self, session_id: str) -> VoiceSessionState | None:
        doc = await self._db[SESSIONS].find_one({"_id": session_id})
        return document_to_session(doc) if doc else None

    async def latest_session_for_student(
        self, student_id: str, *, course_id: str | None = None, lesson_id: str | None = None
    ) -> VoiceSessionState | None:
        query: dict[str, Any] = {"student_id": student_id}
        if course_id:
            query["course_id"] = course_id
        if lesson_id:
            query["lesson_id"] = lesson_id
        doc = await self._db[SESSIONS].find_one(query, sort=[("updated_at", -1)])
        return document_to_session(doc) if doc else None

    async def list_sessions(self, student_id: str, limit: int = 20) -> list[VoiceSessionState]:
        cursor = self._db[SESSIONS].find({"student_id": student_id}).sort("updated_at", -1).limit(limit)
        return [document_to_session(doc) async for doc in cursor]

    async def append_checkpoint(self, doc: CheckpointDoc) -> None:
        await self._db[CHECKPOINTS].insert_one({**doc.model_dump(), "timestamp": doc.created_at})

    async def append_interaction(self, doc: InteractionDoc) -> None:
        await self._db[INTERACTIONS].insert_one(doc.model_dump())

    async def upsert_question(self, doc: QuestionDoc) -> None:
        await self._db[QUESTIONS].replace_one(
            {"question_id": doc.question_id}, {**doc.model_dump(), "timestamp": doc.asked_at}, upsert=True
        )

    async def append_provider_event(self, doc: ProviderEventDoc) -> None:
        await self._db[PROVIDER_EVENTS].insert_one(doc.model_dump())

    async def history(self, session_id: str) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for coll in (CHECKPOINTS, INTERACTIONS, QUESTIONS, PROVIDER_EVENTS):
            cursor = self._db[coll].find({"session_id": session_id}, {"_id": 0}).sort("timestamp", 1)
            out[coll] = [doc async for doc in cursor]
        return out

    async def ping(self) -> bool:
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False

    async def aclose(self) -> None:
        self._client.close()


# --------------------------------------------------------------------------- #


_repository: VoiceRepository | None = None


def build_repository(settings: Settings | None = None) -> VoiceRepository:
    s = settings or get_settings()
    backend = s.voice_persistence_backend
    if backend == "memory":
        return InMemoryVoiceRepository()
    if backend in ("auto", "mongo") and s.effective_mongodb_uri:
        try:
            return MongoVoiceRepository(s.effective_mongodb_uri, s.mongodb_db)
        except Exception as exc:
            if backend == "mongo":
                raise
            log.warning("falling back to in-memory voice persistence", extra={"error_type": type(exc).__name__})
    if backend == "mongo":
        raise RuntimeError("VOICE_PERSISTENCE_BACKEND=mongo but MONGODB_URI is not set")
    return InMemoryVoiceRepository()


def get_repository(settings: Settings | None = None) -> VoiceRepository:
    global _repository
    if _repository is None:
        _repository = build_repository(settings)
    return _repository


def set_repository(repo: VoiceRepository | None) -> None:
    """Test hook."""
    global _repository
    _repository = repo
