"""Arabic over the REST API: one register, and the older spellings still work.

Round-17 clients sent `{"language": "ar-MSA"}` (and before that `"ar-EG"`) where
the service now expects `{"language": "ar", "dialect": "…"}`. Neither may fail:
they start a normal fusHa lesson, and the session reports `dialect: "ar-MSA"`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"language": "ar"}, "ar-MSA"),                       # default stays fusHa
        ({"language": "ar-MSA"}, "ar-MSA"),
        ({"language": "ar-EG"}, "ar-EG"),                     # round-24: real register
        ({"language": "ar", "dialect": "egyptian"}, "ar-EG"),
        ({"language": "ar", "dialect": "msa"}, "ar-MSA"),
    ],
)
def test_every_arabic_spelling_starts_the_right_register(
    client: TestClient, payload: dict, expected: str
):
    response = client.post(
        "/voice/session", json={"student_id": "s1", "topic": "Binary Search", **payload}
    )
    assert response.status_code == 201, response.text
    session_id = response.json()["session_id"]

    state = client.get(f"/voice/session/{session_id}/state").json()
    assert state["language"] == "ar"
    assert state["dialect"] == expected

    caps = client.get("/voice/languages").json()["languages"]
    arabic = next(l for l in caps if l["code"] == "ar")
    assert [d["code"] for d in arabic["dialects"]] == ["ar-MSA", "ar-EG"]


def test_an_unknown_language_is_still_rejected(client: TestClient):
    response = client.post("/voice/session", json={"student_id": "s1", "language": "xx"})
    assert response.status_code == 422
    assert "language must be one of" in response.text


def test_the_two_registers_are_distinct_sessions_with_the_same_lesson(client: TestClient):
    """The register switch itself is exercised in the unit suite (mock providers);
    here we assert the REST surface offers both and keeps the lesson identical."""
    fus = client.post(
        "/voice/session", json={"student_id": "s1", "language": "ar", "topic": "Binary Search"}
    ).json()["session_id"]
    egy = client.post(
        "/voice/session", json={"student_id": "s1", "language": "ar", "dialect": "ar-EG", "topic": "Binary Search"}
    ).json()["session_id"]

    assert client.get(f"/voice/session/{fus}/state").json()["dialect"] == "ar-MSA"
    assert client.get(f"/voice/session/{egy}/state").json()["dialect"] == "ar-EG"
    for sid in (fus, egy):
        assert client.get(f"/voice/session/{sid}/state").json()["current_topic"] == "Binary Search"

    # Switching back to the very same register is a harmless no-op (no reconnect).
    noop = client.post(f"/voice/session/{fus}/language", json={"language": "ar-MSA"})
    assert noop.status_code == 200, noop.text
