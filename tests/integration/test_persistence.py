"""Persistence contract (§30, §57). The in-memory repository is the reference
implementation; MongoVoiceRepository implements the same ABC."""

from __future__ import annotations

import inspect

from app.persistence.repository import (
    InMemoryVoiceRepository,
    MongoVoiceRepository,
    VoiceRepository,
)
from app.voice.state import VoiceSessionState


def test_mongo_repository_implements_the_whole_contract():
    required = [
        name
        for name, member in inspect.getmembers(VoiceRepository, predicate=inspect.isfunction)
        if getattr(member, "__isabstractmethod__", False)
    ]
    assert required
    for name in required:
        assert not getattr(getattr(MongoVoiceRepository, name), "__isabstractmethod__", False), name
        assert not getattr(getattr(InMemoryVoiceRepository, name), "__isabstractmethod__", False), name


async def test_round_trip_and_latest_lookup():
    repo = InMemoryVoiceRepository()
    first = VoiceSessionState(student_id="s1", course_id="c1", lesson_id="l1", language="sw")
    await repo.save_session(first)
    second = VoiceSessionState(student_id="s1", course_id="c1", lesson_id="l1", language="sw")
    second.created_at = first.created_at + 10
    second.updated_at = second.created_at
    await repo.save_session(second)

    latest = await repo.latest_session_for_student("s1", course_id="c1", lesson_id="l1")
    assert latest.session_id == second.session_id
    assert await repo.latest_session_for_student("unknown") is None

    loaded = await repo.get_session(first.session_id)
    assert loaded.language == "sw"


async def test_events_and_provider_history_are_appended(session, repository):
    await session.start()
    await session.interrupt()
    await session.ask_question("Why?")
    await session.end()

    history = await repository.history(session.state.session_id)
    assert history["voice_interactions"], "interaction records must be stored"
    assert history["voice_checkpoints"], "checkpoints must be stored"
    assert history["voice_questions"]
    assert history["voice_provider_events"]
    kinds = {e["kind"] for e in history["voice_provider_events"]}
    assert "selected" in kinds


async def test_session_survives_a_manager_restart(manager, repository, settings, mock_factory, router, rag, progress, orchestrator):
    from app.voice.session_manager import VoiceSessionManager

    session = await manager.create(student_id="s9", language="fr", topic="Recherche binaire")
    await session.start()
    await session.interrupt()
    sid = session.state.session_id
    await manager.shutdown()

    fresh = VoiceSessionManager(
        settings=settings,
        repository=repository,
        router=router,
        factory=mock_factory,
        rag=rag,
        progress=progress,
        orchestrator=orchestrator,
    )
    revived = await fresh.get(sid)
    assert revived is not None
    assert revived.state.language == "fr"
    assert revived.state.resume_checkpoint is not None
    assert revived.state.interrupt_count == 1
