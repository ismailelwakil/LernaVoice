"""Shared fixtures. No test requires a real API key or a real database."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.config import Settings

# Tests never read the developer's `.env`. A real vendor key on disk must not
# change what a test exercises: the suite stays offline and free, and no test may
# silently start depending on a paid credential either. Tests that need a keyed
# configuration build their own `Settings(...)` explicitly.
Settings.model_config["env_file"] = None
from app.learner.orchestrator_adapter import NextAction
from app.learner.progress_adapter import LearnerContext
from app.persistence.repository import InMemoryVoiceRepository, set_repository
from app.providers.factory import ProviderFactory, set_factory
from app.providers.health import ProviderHealthRegistry
from app.providers.mock.providers import (
    INJECTOR,
    MockLLMProvider,
    MockRAGProvider,
    MockRealtimeProvider,
    MockSTTProvider,
    MockTTSProvider,
)
from app.voice.events import EventType, VoiceEvent
from app.voice.provider_router import VoiceProviderRouter
from app.voice.session_manager import VoiceSession, VoiceSessionManager, set_manager

ALL_VENDORS = ("gemini", "elevenlabs", "deepgram", "lerna")


@pytest.fixture(autouse=True)
def _reset_injector():
    INJECTOR.heal()
    yield
    INJECTOR.heal()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        voice_provider_mode="auto",
        voice_fallback_enabled=True,
        voice_max_retries=1,
        voice_retry_backoff=0.0,
        voice_provider_timeout=5.0,
        voice_circuit_breaker_threshold=3,
        voice_circuit_breaker_cooldown=30.0,
        voice_persistence_backend="memory",
        lerna_integration_mode="disabled",
        voice_auth_required=False,
        voice_service_api_key=None,
        log_level="WARNING",
    )


@pytest.fixture
def mock_factory(settings: Settings) -> ProviderFactory:
    """Real capability matrix + real router, but every vendor is a mock object."""
    factory = ProviderFactory(settings)
    factory._realtime.clear()
    factory._stt.clear()
    factory._tts.clear()
    factory._llm.clear()

    factory.register("realtime", "gemini", lambda: MockRealtimeProvider("gemini", reply="Gemini tutor speaking."))
    factory.register("llm", "gemini", lambda: MockLLMProvider("gemini", reply="Gemini composed answer."))
    factory.register("tts", "gemini", lambda: MockTTSProvider("gemini"))
    factory.register("stt", "elevenlabs", lambda: MockSTTProvider("elevenlabs"))
    factory.register("tts", "elevenlabs", lambda: MockTTSProvider("elevenlabs"))
    factory.register("llm", "lerna", lambda: MockLLMProvider("lerna", reply="LERNA pool answer."))
    factory.register("stt", "deepgram", lambda: MockSTTProvider("deepgram"))
    factory.register("tts", "deepgram", lambda: MockTTSProvider("deepgram"))
    set_factory(factory)
    yield factory
    set_factory(None)


@pytest.fixture
def dialogue_factory(settings: Settings) -> ProviderFactory:
    """Like `mock_factory`, but the mocks are not given a canned line.

    Without a canned reply the provider runs the plan-driven dialogue
    (`app/providers/mock/dialogue.py`): it greets in the session language, teaches
    one step, checks in, and reacts to what the student says.
    """
    factory = ProviderFactory(settings)
    factory._realtime.clear()
    factory._stt.clear()
    factory._tts.clear()
    factory._llm.clear()

    factory.register("realtime", "gemini", lambda: MockRealtimeProvider("gemini"))
    factory.register("llm", "gemini", lambda: MockLLMProvider("gemini"))
    factory.register("tts", "gemini", lambda: MockTTSProvider("gemini"))
    factory.register("stt", "elevenlabs", lambda: MockSTTProvider("elevenlabs"))
    factory.register("tts", "elevenlabs", lambda: MockTTSProvider("elevenlabs"))
    factory.register("llm", "lerna", lambda: MockLLMProvider("lerna"))
    factory.register("stt", "deepgram", lambda: MockSTTProvider("deepgram"))
    factory.register("tts", "deepgram", lambda: MockTTSProvider("deepgram"))
    set_factory(factory)
    yield factory
    set_factory(None)


@pytest.fixture
async def dialogue_session(
    settings, repository, router, dialogue_factory, rag, progress, orchestrator
):
    """A session whose mock tutor actually converses (no canned reply)."""
    mgr = VoiceSessionManager(
        settings=settings,
        repository=repository,
        router=router,
        factory=dialogue_factory,
        rag=rag,
        progress=progress,
        orchestrator=orchestrator,
    )
    set_manager(mgr)
    session = await mgr.create(student_id="student-002", language="en", topic="Binary Search")
    yield session
    set_manager(None)


@pytest.fixture
def health(settings: Settings) -> ProviderHealthRegistry:
    return ProviderHealthRegistry(
        failure_threshold=settings.voice_circuit_breaker_threshold,
        cooldown=settings.voice_circuit_breaker_cooldown,
    )


@pytest.fixture
def router(settings: Settings, health: ProviderHealthRegistry) -> VoiceProviderRouter:
    return VoiceProviderRouter(settings=settings, health=health, available_providers=ALL_VENDORS)


@pytest.fixture
def repository() -> InMemoryVoiceRepository:
    repo = InMemoryVoiceRepository()
    set_repository(repo)
    yield repo
    set_repository(None)


class StubProgress:
    def __init__(self) -> None:
        self.signals: list[Any] = []

    async def get_context(self, student_id: str) -> LearnerContext:
        return LearnerContext(
            student_id=student_id,
            name="Test Student",
            course="Algorithms",
            weak_concepts=["recursion"],
            misconceptions=["binary search works on unsorted arrays"],
        )

    async def record_signal(self, student_id: str, signal: Any, *, session_id: str | None = None) -> bool:
        self.signals.append(signal)
        return True


class StubOrchestrator:
    def __init__(self) -> None:
        self.registered: list[tuple[str, str, str | None]] = []

    async def next_action(self, student_id: str) -> NextAction:
        return NextAction(action="continue_lesson", concept="Binary Search")

    async def register_modality(self, student_id: str, session_id: str, lesson_id: str | None) -> None:
        self.registered.append((student_id, session_id, lesson_id))


@pytest.fixture
def progress() -> StubProgress:
    return StubProgress()


@pytest.fixture
def orchestrator() -> StubOrchestrator:
    return StubOrchestrator()


@pytest.fixture
def rag() -> MockRAGProvider:
    return MockRAGProvider()


@pytest.fixture
def manager(settings, repository, router, mock_factory, rag, progress, orchestrator) -> VoiceSessionManager:
    mgr = VoiceSessionManager(
        settings=settings,
        repository=repository,
        router=router,
        factory=mock_factory,
        rag=rag,
        progress=progress,
        orchestrator=orchestrator,
    )
    set_manager(mgr)
    yield mgr
    set_manager(None)


class EventRecorder:
    """Collects every event a session emits."""

    def __init__(self, session: VoiceSession):
        self.session = session
        self.queue = session.subscribe()
        self.events: list[VoiceEvent] = []

    async def drain(self, settle: float = 0.05) -> list[VoiceEvent]:
        await asyncio.sleep(settle)
        while not self.queue.empty():
            self.events.append(self.queue.get_nowait())
        return self.events

    def types(self) -> list[str]:
        return [e.event.value for e in self.events]

    @property
    def last_seq(self) -> int:
        """Sequence of the newest event seen so far — a watermark for "since when?"."""
        return max((e.seq for e in self.events), default=0)

    def of(self, event_type: EventType) -> list[VoiceEvent]:
        return [e for e in self.events if e.event is event_type]

    def has(self, event_type: EventType) -> bool:
        return any(e.event is event_type for e in self.events)


@pytest.fixture
def recorder():
    return EventRecorder


@pytest.fixture
async def session(manager: VoiceSessionManager) -> VoiceSession:
    s = await manager.create(
        student_id="student-001",
        language="en",
        course_id="algorithms-101",
        lesson_id="lesson-binary-search",
        topic="Binary Search",
    )
    return s
