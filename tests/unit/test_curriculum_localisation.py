"""The plan is written in English; the tutor must *speak* the student's language.

Curated translations cover the demo topics (`app/curriculum_localisation.py`).
Everything else keeps the older behaviour (plan read as written), which is what
limitation 13 of the implementation report describes.
"""

from __future__ import annotations

from app.curriculum import resolve
from app.curriculum_localisation import (
    LOCALISED_STEPS,
    covered_topics,
    localise_sections,
    localise_step,
    localise_topic,
)
from app.prompts.interaction import speakable
from app.providers.mock.dialogue import TutorDialogue


def _metadata(topic_id: str, topic_title: str, sections) -> dict:
    return {
        "topic_id": topic_id,
        "topic_title": topic_title,
        "sections": [{"title": s.title, "goal": s.goal} for s in sections],
    }


def test_binary_search_is_fully_arabic_when_spoken():
    topic = resolve("binary-search")
    dialogue = TutorDialogue.from_metadata(_metadata("binary-search", topic.title, topic.sections), "ar")
    said = [dialogue.opening()] + [dialogue.respond("ماشي"), dialogue.respond("مش فاهم"), dialogue.respond("أيوه")]
    blob = " ".join(said)
    for english in (
        "The idea of halving",
        "Trace it on a small array",
        "compare with the middle",
        "walk through 16 elements",
    ):
        assert english.lower() not in blob.lower(), f"English plan leaked into Arabic: {blob}"
    assert "البحث الثنائي" in blob, blob
    assert "فكرة التنصيف" in blob, blob


def test_english_sessions_are_untouched():
    topic = resolve("binary-search")
    dialogue = TutorDialogue.from_metadata(_metadata("binary-search", topic.title, topic.sections), "en")
    opening = dialogue.opening()
    assert "Binary Search" in opening and "the idea of halving" in opening.lower(), opening


def test_an_uncurated_topic_falls_back_to_the_plan_as_written():
    topic = resolve("limits")
    sections = [{"title": s.title, "goal": s.goal} for s in topic.sections]
    out = localise_sections("ar", "limits", sections)
    assert [s["title"] for s in out] == [s["title"] for s in sections]
    assert all(s["localised"] is False for s in out)


def test_every_curated_translation_is_complete_and_used_by_a_real_topic():
    for language, topics in LOCALISED_STEPS.items():
        for topic_key, steps in topics.items():
            topic = resolve(topic_key)
            assert topic is not None, topic_key
            titles = {s.title for s in topic.sections}
            for english_title, (local_title, local_goal) in steps.items():
                assert english_title in titles, f"{topic_key}: '{english_title}' is not a real step"
                assert local_title.strip() and local_goal.strip(), english_title
                # the translation must not silently be the English text again
                spoken = speakable(local_title + " " + local_goal)
                assert not any(ch.isascii() and ch.isalpha() for ch in local_title), local_title
                assert " — " not in spoken, spoken


def test_goal_and_title_lookups():
    title, goal = localise_step("ar", "binary-search", "Common mistakes", "unsorted input")
    assert title == "الأخطاء الشائعة" and "overflow" in goal
    # an unknown language or topic leaves the plan alone
    assert localise_step("sw", "binary-search", "Common mistakes", "unsorted input") == (
        "Common mistakes",
        "unsorted input",
    )
    assert localise_topic("ar", "recursion", "Recursion and the Call Stack") == "الاستدعاء الذاتي"
    assert localise_topic("zu", "recursion", "Recursion and the Call Stack") == "Recursion and the Call Stack"
    # Round 22: the biology plans are localised too, so Arabic covers them as well.
    assert covered_topics("ar") == [
        "binary-search", "cell-structure", "dna-rna",
        "merge-sort", "photosynthesis", "recursion",
    ]


def test_arabic_uses_arabic_punctuation_when_restating_a_step():
    topic = resolve("binary-search")
    dialogue = TutorDialogue.from_metadata(_metadata("binary-search", topic.title, topic.sections), "ar")
    dialogue.opening()
    for _ in range(2):
        line = speakable(dialogue.respond("مش فاهم"))
        assert " — " not in line, line
        assert ", " not in line or "\u060c" in line, line
