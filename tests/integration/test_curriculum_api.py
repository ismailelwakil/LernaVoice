"""The catalogue over the API, and what a chosen topic does to a session.

This is the path the topic picker takes: read `/curriculum/courses`, pick a
`topic_id`, create a session with it, then check the tutor actually received that
lesson plan (state, lesson context and provider metadata).
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_courses_endpoint_lists_topics(client: TestClient):
    body = client.get("/curriculum/courses").json()
    assert body["count"] >= 4
    assert body["stats"]["topics"] >= 15
    first = body["courses"][0]
    assert first["topics"], "each course must list its topics"
    assert first["topics"][0]["sections"], "topics must carry a section plan"


def test_topics_can_be_filtered(client: TestClient):
    all_topics = client.get("/curriculum/topics").json()
    assert all_topics["count"] == len(all_topics["topics"])

    filtered = client.get("/curriculum/topics", params={"course_id": "algorithms-101"}).json()
    assert filtered["count"] >= 3
    assert all(t["course_id"] == "algorithms-101" for t in filtered["topics"])

    beginner = client.get("/curriculum/topics", params={"level": "beginner"}).json()
    assert all(t["level"] == "beginner" for t in beginner["topics"])


def test_single_topic_endpoint_and_404(client: TestClient):
    body = client.get("/curriculum/topics/binary-search").json()
    assert body["topic"]["title"] == "Binary Search"
    assert body["course"]["id"] == "algorithms-101"
    assert client.get("/curriculum/topics/nope").status_code == 404


def test_session_created_from_a_topic_id_carries_the_lesson_plan(client: TestClient):
    created = client.post(
        "/voice/session",
        json={"student_id": "s-1", "language": "en", "topic_id": "binary-search"},
    )
    assert created.status_code == 201
    sid = created.json()["session_id"]

    state = client.get(f"/voice/session/{sid}/state").json()
    assert state["current_topic"] == "Binary Search"
    assert state["topic_id"] == "binary-search"
    assert [s["title"] for s in state["lesson_plan"]][:2] == [
        "The idea of halving",
        "Trace it on a small array",
    ]
    assert state["checkpoint"] is None  # nothing covered yet


def test_topic_id_sets_course_and_lesson_when_the_client_sends_none(client: TestClient):
    sid = client.post(
        "/voice/session", json={"student_id": "s-2", "topic_id": "photosynthesis"}
    ).json()["session_id"]
    state = client.get(f"/voice/session/{sid}/state").json()
    assert state["language"] == "en"
    summary = client.get(f"/voice/session/{sid}").json()
    assert summary["lesson_id"] == "photosynthesis"
    assert summary["course_id"] == "biology-1"


def test_free_text_topic_still_resolves_to_the_catalogue(client: TestClient):
    sid = client.post(
        "/voice/session", json={"student_id": "s-3", "topic": "merge sort"}
    ).json()["session_id"]
    state = client.get(f"/voice/session/{sid}/state").json()
    assert state["topic_id"] == "merge-sort"
    assert state["lesson_plan"], "free-text titles must still produce a plan"


def test_session_without_a_topic_still_works(client: TestClient):
    sid = client.post(
        "/voice/session", json={"student_id": "s-4", "topic": "Something uncatalogued"}
    ).json()["session_id"]
    state = client.get(f"/voice/session/{sid}/state").json()
    assert state["topic_id"] is None
    assert state["lesson_plan"] == []
    assert state["current_topic"] == "Something uncatalogued"


async def test_tutor_receives_the_lesson_plan(manager):
    """The plan must reach the provider: instruction text *and* metadata.

    Driven through the session manager (mock providers), because a realtime
    handshake needs vendor credentials this suite deliberately does not have.
    """
    from app.providers.mock.providers import MockRealtimeProvider

    session = await manager.create(
        student_id="s-5", language="en", topic_id="newton-laws", course_id=None, lesson_id=None
    )
    await session.start()
    await asyncio.sleep(0)  # let the event pump attach the provider

    assert isinstance(session.provider, MockRealtimeProvider)
    config = session.provider.config
    assert config.metadata["topic_title"] == "Newton's Laws"
    assert [s["title"] for s in config.metadata["sections"]][0] == "Inertia"
    assert "Inertia" in config.system_instruction
    assert "Teach the plan in order" in config.system_instruction
    assert session.state.lesson_plan[0]["title"] == "Inertia"
