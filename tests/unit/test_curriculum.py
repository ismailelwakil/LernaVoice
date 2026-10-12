"""The course catalogue the tutor teaches from (app/curriculum.py).

The catalogue is content, so these tests are mostly integrity checks: every
topic is complete enough to teach, ids are unique, and free-text topic names
resolve to a topic so a client that only has a string still gets a lesson plan.
"""

from __future__ import annotations

from app import curriculum
from app.voice.state import LANGUAGE_NAMES, SUPPORTED_LANGUAGES


def test_catalogue_is_not_empty_and_well_formed():
    stats = curriculum.stats()
    assert stats["courses"] >= 4, "the picker should offer several courses"
    assert stats["topics"] >= 15
    assert stats["sections"] >= stats["topics"] * 3, "every topic needs a multi-step plan"


def test_ids_are_unique():
    ids = [t.id for t in curriculum.TOPICS]
    assert len(ids) == len(set(ids))
    course_ids = [c.id for c in curriculum.COURSES]
    assert len(course_ids) == len(set(course_ids))


def test_every_topic_is_teachable():
    for topic in curriculum.TOPICS:
        assert topic.title and topic.summary
        assert len(topic.sections) >= 3, f"{topic.id} needs at least three lesson steps"
        assert len(topic.concepts) >= 3, f"{topic.id} should name its concepts"
        for section in topic.sections:
            assert section.title and section.goal
        assert curriculum.get_course(topic.course_id) is not None


def test_lesson_plan_shape_matches_what_sessions_store():
    plan = curriculum.get_topic("binary-search").lesson_plan()
    assert isinstance(plan, list) and plan
    assert set(plan[0]) == {"title", "goal"}


def test_resolution_by_id_title_and_free_text():
    assert curriculum.resolve("hash-tables").title == "Hash Tables"
    assert curriculum.resolve(topic="Binary Search").id == "binary-search"
    assert curriculum.resolve(topic="merge sort").id == "merge-sort"          # case-insensitive
    assert curriculum.resolve(topic="Recursion").id == "recursion"            # partial title
    assert curriculum.resolve("no-such-topic", "no such topic") is None


def test_catalogue_covers_the_languages_the_service_supports():
    """Nothing in the catalogue is language-specific, but the demo must be able
    to greet in every mandatory language (§25)."""
    # One entry per language: Arabic is taught in fusHa, but it is still `ar`
    # and still one greeting (see app/voice/dialects.py).
    # the ten languages, plus the optional polite-Egyptian register (round 24)
    assert set(curriculum.LOCALISED_GREETINGS) == set(SUPPORTED_LANGUAGES) | {"ar-eg"}
    assert len(LANGUAGE_NAMES) == 10
    for code, phrase in curriculum.LOCALISED_GREETINGS.items():
        assert phrase.strip(), f"empty greeting for {code}"


def test_as_dict_is_serialisable():
    import json

    payload = json.dumps(curriculum.list_courses())
    assert "binary-search" in payload
    container = json.loads(payload)
    assert container[0]["topics"][0]["sections"][0]["goal"]
