"""Round 19, end to end: adding a topic teaches it from vetted sources, at the
student's level — over the REST API, over the socket, and through the offline mock.

The demo has no vendor keys, so what is asserted here is exactly what the demo
proves: the same topic, the same lesson plan, three different explanations.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.learner.profiles import LearnerProfileStore
from app.providers.mock.dialogue import TutorDialogue
from app.voice.session_manager import get_manager

TOPIC = "binary-search"


@pytest.fixture
def client() -> TestClient:
    # The manager is a module-level singleton, so a level written by one test would
    # otherwise decide the next test's profile lookup.
    get_manager().profiles = LearnerProfileStore(None)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def ws_client(manager, repository, mock_factory):
    """The real app with mock providers, for the socket test (§34)."""
    from app.persistence.repository import set_repository
    from app.providers.factory import set_factory
    from app.voice.session_manager import set_manager

    with TestClient(app) as c:
        set_repository(repository)
        set_factory(mock_factory)
        set_manager(manager)
        yield c


def _create(client: TestClient, **payload) -> dict:
    body = {"student_id": "s1", "language": "en", "topic_id": TOPIC, "topic": "Binary Search"}
    body.update(payload)
    response = client.post("/voice/session", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _await(ws, event: str, limit: int = 40) -> dict:
    for _ in range(limit):
        message = ws.receive_json()
        if message.get("event") == event:
            return message
    raise AssertionError(f"{event} was never emitted")


# --------------------------------------------------------------------------- #
# REST
# --------------------------------------------------------------------------- #


def test_a_session_is_pitched_at_the_level_it_was_asked_for(client: TestClient):
    summary = _create(client, level="beginner")
    assert summary["student_level"] == "beginner"

    state = client.get(f"/voice/session/{summary['session_id']}/state").json()
    assert state["student_level"] == "beginner"
    explanation = state["explanation"]
    assert explanation["grounding"] == "curated"
    assert explanation["moves"], "the explanation must carry its teaching moves"
    assert explanation["sources"], "and the sources those moves came from"
    assert explanation["moves"][-1]["kind"] == "check"
    # Every level's facts are the canonical English ones, whatever the lesson language.
    assert all(move["english"] for move in explanation["moves"])


def test_the_level_can_be_changed_mid_lesson_without_losing_anything(client: TestClient):
    summary = _create(client, level="beginner")
    sid = summary["session_id"]

    # Pretend the lesson is under way: a concept has been understood.
    session = get_manager()._sessions[sid]
    session.state.concepts_covered.append("The idea of halving")
    before = client.get(f"/voice/session/{sid}/state").json()

    changed = client.post(f"/voice/session/{sid}/level", json={"level": "advanced"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["detail"] == "level=advanced"

    after = client.get(f"/voice/session/{sid}/state").json()
    assert after["student_level"] == "advanced"
    assert after["current_topic"] == before["current_topic"]
    assert after["concepts_covered"] == before["concepts_covered"]
    # The explanation is rebuilt by level: the closing question is a different one.
    assert after["explanation"]["level"] == "advanced"
    assert after["explanation"]["moves"][-1]["english"] != (
        before["explanation"]["moves"][-1]["english"]
    )


def test_the_level_defaults_to_the_students_profile(client: TestClient):
    """No level in the request -> whatever the profile says, then the default."""
    assert _create(client)["student_level"] == "intermediate"

    manager = get_manager()
    manager.profiles.upsert("s2", level="beginner")
    summary = _create(client, student_id="s2")
    assert summary["student_level"] == "beginner"


@pytest.mark.parametrize("level", ["wizard", "", "a4", "level-9"])
def test_an_unknown_level_is_a_client_error(client: TestClient, level):
    response = client.post(
        "/voice/session", json={"student_id": "s1", "topic_id": TOPIC, "level": level}
    )
    assert response.status_code == 422, response.text
    assert "level must be one of" in response.text


def test_an_unknown_level_cannot_be_switched_to_either(client: TestClient):
    sid = _create(client)["session_id"]
    response = client.post(f"/voice/session/{sid}/level", json={"level": "genius"})
    assert response.status_code == 422
    assert client.get(f"/voice/session/{sid}/state").json()["student_level"] == "intermediate"


# --------------------------------------------------------------------------- #
# what the providers are told
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_the_session_instruction_carries_the_grounding_block():
    from app.learner.profiles import LearnerProfileStore

    manager = get_manager()
    manager.profiles = LearnerProfileStore(None)
    session = await manager.create(
        student_id="s3", language="en", topic_id=TOPIC, topic="Binary Search", level="beginner"
    )
    config = await session._build_session_config()

    instruction = config.system_instruction or ""
    assert "EXPLANATION PLAN" in instruction
    assert "Student level: beginner" in instruction
    assert session.explanation.sources[0].publisher in instruction
    # The mock is told the very same thing, so the offline demo teaches it too.
    assert config.metadata["explanation"]["moves"]
    assert config.metadata["student_level"] == "beginner"


def test_the_offline_tutor_speaks_the_grounded_content(client: TestClient):
    from app.learning.explainer import build_brief

    for level, expected in (("beginner", "sorted"), ("advanced", "sorted")):
        brief = build_brief(topic_id=TOPIC, language="en", level=level)
        dialogue = TutorDialogue.from_metadata(
            {
                "topic_title": "Binary Search",
                "sections": [{"title": s["title"], "goal": s.get("goal", "")}
                             for s in brief.plan],
                "explanation": brief.as_dict(),
                "student_level": level,
            },
            "en",
        )
        opening = dialogue.opening()
        grounded = {move.text.split(".")[0] for move in brief.moves if move.kind != "check"}
        assert any(fragment[:24] in opening for fragment in grounded), opening
        # Nothing from the plan-only wording, and the closing question stays last.
        assert dialogue.check_line() == brief.check_move().text
        # It still keeps teaching rather than checking after every step.
        assert not dialogue.opening().rstrip().endswith("?")


# --------------------------------------------------------------------------- #
# the socket
# --------------------------------------------------------------------------- #


def test_the_explanation_is_announced_on_the_socket(ws_client):
    sid = _create(ws_client, level="advanced")["session_id"]
    with ws_client.websocket_connect(f"/voice/session/{sid}/audio") as ws:
        _await(ws, "session.state_changed")
        ws.send_json({"type": "start"})
        planned = _await(ws, "explanation.planned")
    assert planned["level"] == "advanced"
    assert planned["grounding"] == "curated"
    assert planned["move_count"] >= 4
    assert planned["sources_used"], "the event names the sources it will teach from"
    assert planned["teaching_order"][-1] == "check"
