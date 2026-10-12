"""Round 19: the grounded, level-adapted explanation layer.

Three claims are pinned here, because they are what the round asked for:

1. *grounded* — an explanation is built from the sources this service vetted for the
   topic, and the build carries the source ids so the live model can be held to them;
2. *level-adapted* — the same topic is taught in a different order, with different
   demands, for a beginner, an intermediate and an advanced student;
3. *stored per student* — the level comes from the profile (LERNA's when it answers,
   the local mirror meanwhile), and the profile round-trips on disk.
"""

from __future__ import annotations

import json

import pytest

from app.learner.profiles import LearnerProfileStore, resolve_profile
from app.learning.explainer import build_brief
from app.learning.levels import (
    is_known_level,
    level_options,
    normalise_level,
    style_for,
)
from app.learning.sources import ARABIC_READY, all_sources, pack_for, sources_for

LEVELS = ("beginner", "intermediate", "advanced")
TOPIC = "binary-search"


# --------------------------------------------------------------------------- #
# levels
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "written,expected",
    [
        ("beginner", "beginner"),
        ("Beginner", "beginner"),
        ("a1", "beginner"),
        ("a2", "beginner"),
        ("first year", "beginner"),
        ("مبتدئ", "beginner"),
        ("intermediate", "intermediate"),
        ("b1", "intermediate"),
        ("b2", "intermediate"),
        (None, "intermediate"),           # unknown -> the service default
        ("wizard", "intermediate"),
        ("advanced", "advanced"),
        ("c1", "advanced"),
        ("c2", "advanced"),
        ("3", "advanced"),
        ("متقدم", "advanced"),
    ],
)
def test_level_spellings_resolve(written, expected):
    assert normalise_level(written) == expected


def test_a_level_is_recognised_only_when_it_names_one():
    assert is_known_level("advanced") and is_known_level("a1")
    assert not is_known_level(None) and not is_known_level("wizard")


def test_the_three_levels_differ_in_what_they_demand():
    beginner, middle, advanced = (style_for(l) for l in LEVELS)
    assert beginner.max_clause_words < middle.max_clause_words < advanced.max_clause_words
    assert beginner.analogy and not middle.analogy and not advanced.analogy
    assert advanced.reasoning and not beginner.reasoning
    assert advanced.pitfalls == 2 and beginner.pitfalls == 1
    assert (beginner.check, middle.check, advanced.check) == ("closed", "applied", "open")
    assert len({s.instruction for s in (beginner, middle, advanced)}) == 3


def test_the_picker_offers_all_three_levels():
    options = level_options()
    assert [o["code"] for o in options] == list(LEVELS)


# --------------------------------------------------------------------------- #
# sources
# --------------------------------------------------------------------------- #


def test_every_pack_names_where_its_content_came_from():
    packs = {
        title: pack
        for group in all_sources().values()
        for title, pack in [(group[0].publisher, group)]
    }
    assert packs, "no topic packs are defined"
    for pack in all_sources().values():
        assert pack, "an empty group"
        for source in pack:
            assert source.url.startswith("http"), source
            assert source.publisher and source.title and source.why


def test_a_catalogued_topic_has_a_pack_and_an_unknown_one_does_not():
    pack = pack_for(TOPIC)
    assert pack is not None and pack.items
    assert pack_for("no-such-topic") is None
    assert sources_for("no-such-topic") == ()


def test_arabic_is_ready_for_the_topics_it_claims():
    assert len(ARABIC_READY) >= 1
    for topic_id in ARABIC_READY:
        pack = pack_for(topic_id)
        assert pack is not None, topic_id
        assert pack.of("fact") and pack.first("fact").ar, topic_id
        assert pack.first("check") and pack.first("check").ar, topic_id


# --------------------------------------------------------------------------- #
# the brief: grounded, ordered by level
# --------------------------------------------------------------------------- #


def test_the_brief_stays_on_the_sources_it_was_given():
    brief = build_brief(topic_id=TOPIC, language="en", level="intermediate")
    assert brief.grounding == "curated"
    assert brief.sources, "a curated topic must name its sources"
    known = {s.id for s in brief.sources}
    assert all(set(move.sources) <= known for move in brief.moves)
    # Every move can point at where it came from, and the prompt block says so.
    block = brief.prompt_block()
    assert brief.sources[0].publisher in block
    assert "never read a URL aloud" in block


def test_an_unknown_topic_falls_back_to_the_catalogue_plan():
    brief = build_brief(topic_id="no-such-topic", topic_title="Quantum Knitting", language="en")
    assert brief.grounding == "catalogue"
    assert brief.moves == ()
    assert brief.prompt_block() == "" or "EXPLANATION PLAN" not in brief.prompt_block()


@pytest.mark.parametrize("level", LEVELS)
def test_the_explanation_is_ordered_for_the_level(level):
    brief = build_brief(topic_id=TOPIC, language="en", level=level)
    kinds = brief.kinds()
    assert kinds, level
    assert kinds[-1] == "check", f"{level}: the closing question is last"
    assert kinds.count("check") == 1
    # Every lesson part is taught, so a kind may legitimately come back — but the
    # picture belongs to the opening and the question to the close.
    assert "hook" not in kinds[1:], "the picture opens the lesson, or is not used"
    assert brief.check_move() is not None
    assert kinds[-1] == "check"
    if level == "beginner":
        assert "hook" in kinds and "example" in kinds
        assert brief.check_move().text.rstrip().endswith("?")
    if level == "advanced":
        assert "hook" not in kinds and "use" in kinds, kinds
        assert kinds.count("pitfall") >= 2, kinds


def test_level_changes_the_words_not_only_their_order():
    beginner = build_brief(topic_id=TOPIC, language="en", level="beginner")
    advanced = build_brief(topic_id=TOPIC, language="en", level="advanced")
    assert beginner.check_move().text != advanced.check_move().text
    assert beginner.prompt_block() != advanced.prompt_block()
    assert "Student level: beginner" in beginner.prompt_block()
    assert "Student level: advanced" in advanced.prompt_block()


def test_arabic_explanations_are_spoken_in_arabic_and_recorded_in_english():
    brief = build_brief(topic_id=TOPIC, language="ar", level="beginner")
    for move in brief.moves:
        assert move.english, "the canonical (English) text must always be kept"
        if any(ch > "\u0600" for ch in move.text):
            continue
        pytest.fail(f"move {move.kind} was not translated: {move.text!r}")
    assert brief.frames == "ar"
    assert brief.opening("", brief.topic)  # never empty


def test_an_arabic_lesson_never_falls_back_to_english_sentences():
    """Arabic is fusHa only: an untranslated item is left out, not spoken in English."""
    brief = build_brief(topic_id=TOPIC, language="ar", level="beginner")
    assert brief.grounding == "curated"
    for move in brief.moves:
        assert any("\u0600" <= ch <= "\u06ff" for ch in move.text), move.text
        assert move.english  # ... while the canonical record stays English

    # A topic whose pack has no Arabic yet teaches from the plan instead of
    # lecturing an Arabic lesson in English.
    uncurated = build_brief(topic_id="newton-laws", language="ar", level="beginner")
    assert uncurated.grounding == "catalogue"
    assert uncurated.moves == ()
    assert uncurated.prompt_block() == ""
    # ... and the same topic is fully grounded in English.
    assert build_brief(topic_id="newton-laws", language="en").grounding == "curated"


def test_the_moves_are_shared_across_the_lesson_steps():
    brief = build_brief(topic_id=TOPIC, language="en", level="intermediate", plan=[
        {"title": "What it is", "goal": "…"},
        {"title": "How it works", "goal": "…"},
        {"title": "When it fails", "goal": "…"},
    ])
    seen = [m for step in range(3) for m in brief.for_step(step) if m.kind != "check"]
    taught = [m for m in brief.moves if m.kind != "check"]
    assert {m.kind for m in seen} == {m.kind for m in taught}
    assert len(seen) == len(taught), "a step must not repeat another step's move"
    # ... and the closing question travels with the brief, not with a step.
    assert brief.check_move() is not None


# --------------------------------------------------------------------------- #
# the profile: where the level is kept
# --------------------------------------------------------------------------- #


def test_the_store_round_trips_on_disk(tmp_path):
    path = tmp_path / "learner_profiles.json"
    store = LearnerProfileStore(path)
    store.upsert("s1", level="advanced", name="Mona")
    assert LearnerProfileStore(path).get("s1")["level"] == "advanced"
    assert json.loads(path.read_text(encoding="utf-8"))["s1"]["name"] == "Mona"
    # Unrelated fields survive an update.
    store.upsert("s1", level="beginner")
    assert store.get("s1")["name"] == "Mona"


def test_a_memory_store_writes_nothing(tmp_path):
    store = LearnerProfileStore(None)
    store.upsert("s1", level="beginner")
    assert store.get("s1")["level"] == "beginner"
    assert list(tmp_path.iterdir()) == []


def test_the_request_wins_over_the_profile_which_wins_over_the_default():
    stored = {"level": "beginner"}
    lerna = {"level": "advanced", "name": "Mona", "available": True}
    assert resolve_profile("s1", requested_level="advanced", stored=stored).level == "advanced"
    assert resolve_profile("s1", stored=stored).level == "beginner"
    assert resolve_profile("s1", lerna=lerna).level == "advanced"
    assert resolve_profile("s1").level == "intermediate"
    assert resolve_profile("s1", stored=stored).source == "store"
    assert resolve_profile("s1", lerna=lerna).source == "lerna"


def test_an_offline_lerna_profile_does_not_erase_the_local_level():
    profile = resolve_profile(
        "s1", stored={"level": "advanced"}, lerna={"available": False, "note": "offline"}
    )
    assert profile.level == "advanced"
    assert profile.note == "offline"
