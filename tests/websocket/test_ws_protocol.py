"""WebSocket + REST contract tests (§34, §35, §48)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api.security import token_store
from app.main import app


@pytest.fixture
def client(manager, repository, mock_factory):
    """Real ASGI app, mock providers. The lifespan builds its own singletons, so
    the test doubles are re-installed once startup has finished."""
    from app.persistence.repository import set_repository
    from app.providers.factory import set_factory
    from app.voice.session_manager import set_manager

    with TestClient(app) as c:
        set_repository(repository)
        set_factory(mock_factory)
        set_manager(manager)
        yield c


def _create(client, **overrides):
    payload = {
        "student_id": "student-001",
        "language": "ar",
        "course_id": "algorithms-101",
        "lesson_id": "lesson-binary-search",
        "topic": "Binary Search",
    }
    payload.update(overrides)
    response = client.post("/voice/session", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_health_is_public(client):
    data = client.get("/health").json()
    assert data["status"] == "ok"
    assert data["service"]


def test_provider_health_exposes_matrix_but_no_secrets(client):
    data = client.get("/health/providers").json()
    assert "matrix" in data and "ig" in data["matrix"]
    body = json.dumps(data).lower()
    for leak in ("sk_", "aiza", "mongodb+srv", "api_key\":"):
        assert leak not in body


def test_languages_endpoint_lists_ten(client):
    data = client.get("/voice/languages").json()
    assert data["count"] == 10
    igbo = next(l for l in data["languages"] if l["code"] == "ig")
    assert igbo["realtime_native"] is False
    assert igbo["primary_pipeline"]["mode"] == "cascade"
    # Arabic is taught in fusHa; the register is advertised with the voice it
    # speaks with (see app/voice/dialects.py).
    arabic = next(l for l in data["languages"] if l["code"] == "ar")
    assert [d["code"] for d in arabic["dialects"]] == ["ar-MSA", "ar-EG"]
    assert arabic["dialects"][0]["voice"] == "ar-SA-ZariyahNeural"   # fusHa default
    assert arabic["dialects"][1]["voice"] == "ar-EG-SalmaNeural"     # polite Egyptian
    assert "dialects" not in next(l for l in data["languages"] if l["code"] == "en")


def test_session_crud_and_state(client):
    created = _create(client)
    sid = created["session_id"]
    assert created["websocket_url"].endswith(f"/voice/session/{sid}/audio")

    assert client.get(f"/voice/session/{sid}").status_code == 200
    state = client.get(f"/voice/session/{sid}/state").json()
    assert state["language"] == "ar"
    assert state["diagnostics"]["active_provider"]

    assert client.get("/voice/session/does-not-exist").status_code == 404


def test_rejects_unsupported_language(client):
    response = client.post("/voice/session", json={"student_id": "s", "language": "de"})
    assert response.status_code == 422
    assert response.json()["code"] == "VOICE_REQUEST_INVALID"


def test_rest_interrupt_question_resume_flow(client):
    sid = _create(client, language="en")["session_id"]
    client.post(f"/voice/session/{sid}/start")

    interrupt = client.post(f"/voice/session/{sid}/interrupt").json()
    assert interrupt["acknowledgement"]
    assert interrupt["checkpoint"]["checkpoint_id"]
    assert interrupt["playback_stop_ms"] is not None

    question = client.post(f"/voice/session/{sid}/question", json={"text": "Why halve?"}).json()
    assert question["is_followup"] is False

    resume = client.post(f"/voice/session/{sid}/resume").json()
    assert resume["state"] in ("resuming", "speaking", "listening", "thinking")

    ended = client.post(f"/voice/session/{sid}/end").json()
    assert ended["state"] == "ended"


def test_websocket_stream_and_control_messages(client):
    sid = _create(client, language="en")["session_id"]

    with client.websocket_connect(f"/voice/session/{sid}/audio") as ws:
        hello = ws.receive_json()
        assert hello["event"] == "session.state_changed"
        assert hello["resumed_connection"] is True

        ws.send_json({"type": "ping"})
        assert _await_event(ws, "pong")

        ws.send_json({"type": "start"})
        assert _await_event(ws, "session.started")

        ws.send_bytes(b"\x00\x01" * 320)  # PCM16 frame
        ws.send_json({"type": "interrupt"})
        interrupted = _await_event(ws, "assistant.interrupted")
        assert interrupted["stop_playback"] is True
        checkpoint = _await_event(ws, "checkpoint.created")
        assert checkpoint["checkpoint"]["checkpoint_id"]

        ws.send_json({"type": "question", "text": "Why do we halve the array?"})
        assert _await_event(ws, "question.started")

        ws.send_json({"type": "resume"})
        assert _await_event(ws, "resume.started")

        ws.send_json({"type": "end"})
        assert _await_event(ws, "session.ended")


def test_websocket_events_are_sequenced_for_dedupe(client):
    sid = _create(client)["session_id"]
    with client.websocket_connect(f"/voice/session/{sid}/audio") as ws:
        ws.receive_json()
        ws.send_json({"type": "start"})
        seqs = []
        for _ in range(6):
            event = ws.receive_json()
            if "seq" in event:
                seqs.append(event["seq"])
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)


def test_websocket_base64_audio_fallback(client):
    import base64

    sid = _create(client)["session_id"]
    with client.websocket_connect(f"/voice/session/{sid}/audio") as ws:
        ws.receive_json()
        ws.send_json({"type": "start"})
        _await_event(ws, "session.started")
        ws.send_json({"type": "audio", "audio": base64.b64encode(b"\x00\x01" * 160).decode()})
        ws.send_json({"type": "ping"})
        assert _await_event(ws, "pong")


def test_websocket_unknown_session_is_closed(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/voice/session/nope/audio") as ws:
            ws.receive_json()


def test_reconnect_restores_state_without_restarting(client):
    sid = _create(client, language="en")["session_id"]
    with client.websocket_connect(f"/voice/session/{sid}/audio") as ws:
        ws.receive_json()
        ws.send_json({"type": "start"})
        _await_event(ws, "session.started")
        ws.send_json({"type": "interrupt"})
        _await_event(ws, "checkpoint.created")

    # drop and come back on the same session id
    with client.websocket_connect(f"/voice/session/{sid}/audio") as ws:
        hello = ws.receive_json()
        assert hello["resumed_connection"] is True
        assert hello["checkpoint"] is not None
        assert hello["last_seq"] > 0

    state = client.get(f"/voice/session/{sid}/state").json()
    assert state["checkpoint"] is not None


def test_client_token_authentication(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "voice_service_api_key", "service-secret", raising=False)
    monkeypatch.setattr(settings, "voice_auth_required", True, raising=False)

    headers = {"X-Voice-Service-Key": "service-secret"}
    created = client.post(
        "/voice/session", json={"student_id": "s", "language": "en"}, headers=headers
    ).json()
    sid = created["session_id"]

    assert client.get(f"/voice/session/{sid}").status_code == 401

    token = client.post(f"/voice/session/{sid}/token", headers=headers).json()["token"]
    assert token.startswith("vst_")
    assert token_store.resolve(token) == sid

    with client.websocket_connect(f"/voice/session/{sid}/audio?token={token}") as ws:
        assert ws.receive_json()["event"] == "session.state_changed"

    with pytest.raises(Exception):
        with client.websocket_connect(f"/voice/session/{sid}/audio?token=bogus") as ws:
            ws.receive_json()


def _await_event(ws, event_name: str, limit: int = 40) -> dict:
    for _ in range(limit):
        message = ws.receive_json()
        if message.get("event") == event_name:
            return message
    raise AssertionError(f"event '{event_name}' not observed")


def test_auth_required_with_blank_key_does_not_lock_out_console(client, monkeypatch):
    """Round 31 — the deploy example sets VOICE_AUTH_REQUIRED=true with a blank key.

    Requiring auth against an *empty* key can never succeed and would 401 the
    service's own console, so the service must run open until a real key is set.
    """
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "voice_service_api_key", None, raising=False)
    monkeypatch.setattr(settings, "voice_auth_required", True, raising=False)

    created = client.post("/voice/session", json={"student_id": "s", "language": "en"})
    assert created.status_code == 201          # not locked out
    sid = created.json()["session_id"]
    assert client.get(f"/voice/session/{sid}").status_code == 200
