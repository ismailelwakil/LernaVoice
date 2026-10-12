"""Setup failures must reach the person running the demo with something they can act on."""

from __future__ import annotations

import pytest

from app.providers.hints import setup_hint
from app.voice.events import EventType


@pytest.mark.parametrize(
    "message,fragment",
    [
        (
            "1008 None. This API method requires billing to be enabled. Please enable billing on project #lernavoice",
            "billing/enable?project=lernavoice",
        ),
        ("API key not valid. Please pass a valid API key.", "rejected the credential"),
        ("429 Resource has been exhausted (e.g. check quota).", "quota"),
        ("models/gemini-9-live is not found for API version v1beta", "not available for the configured project"),
        ("The Vertex AI API has not been used in project 12 before or it is disabled.", "aiplatform.googleapis.com"),
        ("Deadline exceeded while waiting for the live session", "VOICE_PROVIDER_TIMEOUT"),
    ],
)
def test_known_setup_failures_explain_themselves(message, fragment):
    hint = setup_hint(message, project="lernavoice")
    assert hint and fragment in hint, hint


def test_a_transient_error_gets_no_hint():
    """A flaky network is not a configuration problem — do not invent advice for it."""
    assert setup_hint("connection reset by peer") is None
    assert setup_hint("") is None


async def test_the_client_receives_the_hint_on_a_failed_session(
    settings, repository, router, mock_factory, rag, progress, orchestrator, recorder
):
    """A session that cannot connect tells the screen *why*, not just 'unavailable'."""
    from app.providers.base import ProviderQuotaError

    class DeadProvider:
        """Every vendor refuses to start, the way an unbilled project does."""

        provider_name = "gemini"

        async def start_session(self, config):  # noqa: ANN001, D401
            raise ProviderQuotaError(
                "1008 None. This API method requires billing to be enabled. "
                "Please enable billing on project #lernavoice",
                provider="gemini",
            )

        async def close_session(self) -> None:
            return None

        def set_tool_handler(self, handler) -> None:  # noqa: ANN001
            return None

        async def interrupt(self) -> None:
            return None

    factory = mock_factory
    for kind, vendor in (
        ("realtime", "gemini"), ("llm", "gemini"), ("tts", "gemini"),
        ("stt", "elevenlabs"), ("tts", "elevenlabs"), ("llm", "lerna"),
        ("stt", "deepgram"), ("tts", "deepgram"),
    ):
        factory.register(kind, vendor, lambda: DeadProvider())

    from app.voice.session_manager import VoiceSessionManager, set_manager

    mgr = VoiceSessionManager(
        settings=settings.model_copy(update={"voice_fallback_enabled": False}),
        repository=repository, router=router, factory=factory,
        rag=rag, progress=progress, orchestrator=orchestrator,
    )
    set_manager(mgr)
    session = await mgr.create(student_id="student-err", language="en", topic="Binary Search")
    rec = recorder(session)

    with pytest.raises(Exception):
        await session.start()
    await rec.drain()
    set_manager(None)

    errors = rec.of(EventType.ERROR)
    assert errors, "a failed start must emit an error event"
    data = errors[-1].data
    assert "billing" in (data.get("hint") or "").lower(), data
    assert "billing" in data["message"].lower(), data
