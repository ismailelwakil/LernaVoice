"""The live-voice configuration: Gemini Live humanising options, and how the service
reports whether a real vendor voice is in play.

Nothing here needs a credential: the Gemini client is replaced by a stub that records
the setup payload it was handed.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.providers.base import SessionConfig
from app.providers.gemini import live as live_module
from app.providers.gemini.live import _looks_like_setup_rejection

SETUP = SessionConfig(
    session_id="s1",
    language="en",
    system_instruction="You are LERNA's Voice Tutor.",
    voice_name="Kore",
    metadata={"sections": [{"title": "A", "goal": "ga"}]},
)


# --------------------------------------------------------------------------- #
# the setup payload
# --------------------------------------------------------------------------- #


class _FakeSession:
    def __init__(self) -> None:
        self.configs: list[dict[str, Any]] = []

    async def send_realtime_input(self, **_kw: Any) -> None:  # pragma: no cover - unused here
        return None


class _FakeConn:
    def __init__(self, recorder: list[dict[str, Any]], fail_first: bool) -> None:
        self.recorder = recorder
        self.fail_first = fail_first

    async def __aenter__(self) -> _FakeSession:
        if self.fail_first and len(self.recorder) == 1:
            raise ValueError("Unknown field: enable_affective_dialog")
        return _FakeSession()

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakeLive:
    def __init__(self, recorder: list[dict[str, Any]], fail_first: bool = False) -> None:
        self.recorder = recorder
        self.fail_first = fail_first

    def connect(self, *, model: str, config: dict[str, Any]) -> _FakeConn:
        self.recorder.append(config)
        return _FakeConn(self.recorder, self.fail_first)


class _FakeAio:
    def __init__(self, live: _FakeLive) -> None:
        self.live = live


class _FakeClient:
    def __init__(self, recorder: list[dict[str, Any]], fail_first: bool = False) -> None:
        self.aio = _FakeAio(_FakeLive(recorder, fail_first))


class _Types:
    """Just enough of `google.genai.types` for the setup payload — no SDK required."""

    class SpeechConfig:
        def __init__(self, **kw: Any) -> None:
            self.kw = kw

    class VoiceConfig:
        def __init__(self, **kw: Any) -> None:
            self.kw = kw

    class PrebuiltVoiceConfig:
        def __init__(self, **kw: Any) -> None:
            self.kw = kw


@pytest.fixture(autouse=True)
def _stub_genai(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite must run with no vendor SDK installed (only the mocks are used).

    One test opts out of this stub to validate the payload against the real SDK when it
    happens to be installed.
    """
    if "real_sdk" in os.environ:
        return
    monkeypatch.setattr(live_module, "genai_types", lambda: _Types)


def _provider(settings: Settings, recorder: list[dict[str, Any]], fail_first: bool = False):
    provider = live_module.GeminiLiveProvider(settings)
    provider._client = _FakeClient(recorder, fail_first)
    return provider


def _settings(**kw: Any) -> Settings:
    """Settings with a Vertex project and **no** `.env` bleed (a real .env must not
    change what these tests assert)."""
    return Settings(
        _env_file=None,
        app_env="test",
        google_genai_use_vertexai=True,
        google_cloud_project="demo-project",
        log_level="WARNING",
        **kw,
    )


async def test_affective_dialog_is_requested_for_the_live_voice():
    """A flat narrator is the complaint this closes: the native-audio model is told to
    adapt to how the student sounds."""
    recorder: list[dict[str, Any]] = []
    provider = _provider(_settings(), recorder)
    await provider.start_session(SETUP)

    assert recorder, "no setup payload was sent"
    assert recorder[0]["enable_affective_dialog"] is True
    assert recorder[0]["response_modalities"] == ["AUDIO"]
    assert recorder[0]["system_instruction"] == SETUP.system_instruction
    # Proactive audio is deliberately off by default: a tutor answers, it does not
    # fill every silence.
    assert "proactivity" not in recorder[0]
    await provider.close_session()


async def test_proactive_audio_can_be_switched_on():
    recorder: list[dict[str, Any]] = []
    provider = _provider(_settings(gemini_proactive_audio=True), recorder)
    await provider.start_session(SETUP)
    assert recorder[0]["proactivity"] == {"proactive_audio": True}
    await provider.close_session()


async def test_a_model_that_rejects_the_extras_still_connects():
    """Older live models may not know these fields; the session must not die for it."""
    recorder: list[dict[str, Any]] = []
    provider = _provider(_settings(), recorder, fail_first=True)
    await provider.start_session(SETUP)          # must not raise

    assert len(recorder) == 2, recorder
    assert "enable_affective_dialog" in recorder[0]
    assert "enable_affective_dialog" not in recorder[1]
    await provider.close_session()


async def test_a_real_connection_error_is_not_retried_as_a_setup_problem():
    """Only setup-shaped failures retry: a network error must fail over immediately."""
    assert _looks_like_setup_rejection(ValueError("Unknown field: proactivity")) is True
    assert _looks_like_setup_rejection(Exception("Invalid JSON payload")) is True
    assert _looks_like_setup_rejection(TimeoutError("connection timed out")) is False
    assert _looks_like_setup_rejection(ConnectionError("connection reset by peer")) is False


# --------------------------------------------------------------------------- #
# what /health says about the voice
# --------------------------------------------------------------------------- #


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_health_reports_the_voice_pipeline_without_credentials(client: TestClient):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["provider_mode"] in ("auto", "gemini_only", "elevenlabs_only", "deepgram_only")
    assert isinstance(body["mock_providers"], bool)
    assert body["gemini_auth"] in ("vertex", "developer_api", "none")
    assert "live_model" in body
    # No secret of any kind may appear in an unauthenticated payload.
    raw = client.get("/health").text.lower()
    for smell in ("api_key", "apikey", "secret", "password", "token", "sk-", "ai za"):
        assert smell not in raw, smell


def test_gemini_auth_mode_is_honest_about_what_is_wired():
    def S(**kw: Any) -> Settings:
        return Settings(_env_file=None, app_env="test", **kw)

    assert S().gemini_auth_mode == "none"
    assert S(gemini_api_key="x").gemini_auth_mode == "developer_api"
    assert S(google_genai_use_vertexai=True, google_cloud_project="p").gemini_auth_mode == "vertex"
    # Vertex selected but nothing to authenticate with is *not* "vertex".
    assert S(google_genai_use_vertexai=True).gemini_auth_mode == "none"


def test_the_demo_prefers_the_vendor_voice_when_providers_are_live(client: TestClient):
    """With real keys the tutor's own neural voice is what should be heard; on the mock
    the browser voice is the clear-sounding option."""
    html = client.get("/").text
    assert "mock_providers === false" in html
    assert "setVoiceMode('service')" in html
    assert "vendor voice" in html


def test_the_setup_payload_is_valid_against_the_real_sdk():
    """The payload we build must be something the installed SDK accepts.

    Skipped when `google-genai` is absent (the suite runs without vendor SDKs), but when
    it *is* installed this catches a field name that the SDK would reject at runtime —
    the difference between a tutor that connects and one that fails over on startup.
    """
    genai_types = pytest.importorskip("google.genai.types")
    import app.providers.gemini.live as live_mod

    original = live_mod.genai_types
    live_mod.genai_types = lambda: genai_types          # use the real SDK this once
    recorder: list[dict[str, Any]] = []
    provider = _provider(_settings(gemini_proactive_audio=True), recorder)
    asyncio.run(provider.start_session(SETUP))

    payload = recorder[0]
    parsed = genai_types.LiveConnectConfig(**payload)
    assert parsed.response_modalities == ["AUDIO"]
    assert parsed.enable_affective_dialog is True
    assert parsed.proactivity.proactive_audio is True
    assert parsed.speech_config.voice_config.prebuilt_voice_config.voice_name == "Kore"
    live_mod.genai_types = original


# --------------------------------------------------------------------------- #
# the credential file the SDK is given
# --------------------------------------------------------------------------- #


def test_the_configured_service_account_file_is_used_explicitly(tmp_path):
    """`.env` does not populate os.environ, so the file must be handed to the SDK.

    Caught live: GOOGLE_APPLICATION_CREDENTIALS sat in `.env`, pydantic-settings read it
    into Settings, the Google SDK read nothing and failed with "default credentials were
    not found" — masking the real (billing) error one layer down.
    """
    from app.providers.base import ProviderAuthError
    from app.providers.gemini.client import _vertex_credentials

    assert _vertex_credentials(Settings(_env_file=None, app_env="test")) is None  # ADC path

    missing = Settings(_env_file=None, app_env="test", google_application_credentials=str(tmp_path / "nope.json"))
    with pytest.raises(ProviderAuthError):
        _vertex_credentials(missing)

    real = "/home/user/lerna/voice-ai/.secrets/vertex-service-account.json"
    if os.path.exists(real):
        creds = _vertex_credentials(
            Settings(_env_file=None, app_env="test", google_application_credentials=real)
        )
        assert creds is not None and creds.service_account_email.endswith("gserviceaccount.com")


def test_settings_read_the_credentials_path_from_env_file():
    """The field exists at all — without it a .env-only setup silently uses ADC."""
    from app.config import Settings as S

    assert "google_application_credentials" in S.model_fields


def test_adc_failure_has_an_actionable_hint():
    from app.providers.hints import setup_hint

    hint = setup_hint("DefaultCredentialsError: Your default credentials were not found.")
    assert hint and "GOOGLE_APPLICATION_CREDENTIALS" in hint
    billing = setup_hint("1008 None. This API method requires billing to be enabled.")
    assert billing and "billing" in billing.lower()
