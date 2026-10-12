"""Concepts are saved in English whatever language the tutor speaks.

The student hears Arabic, French, Swahili…; the Progress Profile, the checkpoints
and the resume instructions must still read like the curriculum, because that is
what the rest of LERNA matches against. No vendor call, no network: the tutoring
runs on the offline policy and the vendor voice is a stub.
"""

from __future__ import annotations

import pytest

from app.curriculum import resolve
from app.learner.canonical_concepts import (
    canonical_topic,
    canonicalise_concept,
    catalogue_concepts,
)
from app.providers.mock.dialogue import TutorDialogue
from app.voice.state import LearningSignal, VoiceSessionState

ARABIC_CONCEPT = "فكرة التنصيف"
ARABIC_GOAL = "نقارن بالعنصر الأوسط، ونُهمل النصف الذي يستحيل أن يحتوي على الهدف"


# --------------------------------------------------------------------------- #
# the resolver
# --------------------------------------------------------------------------- #


def test_an_arabic_concept_is_stored_as_the_english_one():
    concept = canonicalise_concept(ARABIC_CONCEPT, language="ar", topic_id="binary-search")
    assert concept.canonical == "The idea of halving"
    assert concept.spoken == ARABIC_CONCEPT
    assert concept.resolved is True
    assert concept.as_dict()["spoken_as"] == ARABIC_CONCEPT


def test_a_spoken_goal_or_fragment_resolves_too():
    whole = canonicalise_concept(ARABIC_GOAL, language="ar", topic_id="binary-search")
    fragment = canonicalise_concept("النصف الذي يستحيل أن يحتوي على الهدف", language="ar", topic_id="binary-search")
    assert whole.canonical == "The idea of halving"
    assert fragment.canonical == "The idea of halving"


def test_english_is_left_alone_and_paraphrases_snap_to_the_catalogue():
    same = canonicalise_concept("The idea of halving", language="en", topic_id="binary-search")
    assert same.canonical == "The idea of halving" and same.resolved
    # the live model paraphrases in English too; map it when it clearly matches
    paraphrase = canonicalise_concept(
        "we keep halving the range until one element is left", language="en", topic_id="binary-search"
    )
    assert paraphrase.canonical == "we keep halving the range until one element is left"
    assert paraphrase.catalogue_ref == "The idea of halving", "the anchor is what downstream matches on"
    # …but never invent a mapping for something unrelated: no anchor is claimed
    unrelated = canonicalise_concept("let us talk about graphs instead", language="en", topic_id="binary-search")
    assert unrelated.catalogue_ref is None
    assert unrelated.canonical == "let us talk about graphs instead"


def test_unknown_arabic_is_kept_and_flagged_rather_than_guessed():
    concept = canonicalise_concept("حاجة تانية خالص", language="ar", topic_id="binary-search")
    assert concept.canonical == "حاجة تانية خالص"
    assert concept.resolved is False, "a guess would silently corrupt the profile"


def test_topics_are_named_the_catalogue_way():
    assert canonical_topic("binary-search", "البحث الثنائي") == "Binary Search"
    assert canonical_topic("binary-search", "Binary Search") == "Binary Search"
    assert canonical_topic(None, "Protein synthesis") == "Protein synthesis"


def test_catalogue_concepts_are_english_and_ordered():
    concepts = catalogue_concepts("binary-search")
    assert concepts == [
        "The idea of halving",
        "Trace it on a small array",
        "Why the cost is logarithmic",
        "Common mistakes",
    ]
    assert all(c.isascii() for concept in concepts for c in concept)


# --------------------------------------------------------------------------- #
# the session: what actually lands in the state and the profile
# --------------------------------------------------------------------------- #


class StubProgress:
    def __init__(self) -> None:
        self.signals: list[LearningSignal] = []

    async def record_signal(self, student_id, signal, *, session_id=None) -> bool:
        self.signals.append(signal)
        return True


@pytest.mark.asyncio
async def test_an_arabic_session_records_english_concepts(
    dialogue_session, monkeypatch
):
    """Teach Arabic, store English \u2014 through the real tool handler."""
    session = dialogue_session
    session.state.language = "ar"
    session.state.topic_id = "binary-search"
    topic = resolve("binary-search")
    session.state.lesson_plan = [{"title": s.title, "goal": s.goal} for s in topic.sections]
    progress = StubProgress()
    monkeypatch.setattr(session, "progress", progress, raising=False)

    await session._handle_tool("record_learning_signal", {"kind": "concept_understood", "concept": ARABIC_CONCEPT})
    await session._handle_tool("record_learning_signal", {"kind": "concept_discussed", "concept": ARABIC_GOAL})
    await session._handle_tool(
        "record_learning_signal", {"kind": "misconception_detected", "concept": "الأخطاء الشائعة"}
    )
    await session._handle_tool(
        "update_lesson_position", {"topic": "البحث الثنائي", "section": "The idea of halving",
                                   "last_concept": "فكرة التنصيف"}
    )

    assert "The idea of halving" in session.state.concepts_covered
    assert "Common mistakes" in session.state.misconceptions
    assert not any("\u0600" <= ch <= "\u06ff" for c in session.state.concepts_covered for ch in c)
    assert session.state.current_topic == "Binary Search"
    assert all(signal.concept.isascii() for signal in progress.signals), [
        s.concept for s in progress.signals
    ]
    # nothing is lost: what was said is still on the record, with its language
    spoken = [s.spoken_as for s in progress.signals if s.spoken_as]
    assert ARABIC_CONCEPT in spoken and ARABIC_GOAL in spoken
    assert {s.language for s in progress.signals} == {"ar"}


@pytest.mark.asyncio
async def test_an_english_session_is_unchanged(dialogue_session):
    session = dialogue_session
    session.state.topic_id = "binary-search"
    await session._handle_tool(
        "update_lesson_position", {"topic": "Binary Search", "section": "Common mistakes",
                                   "last_concept": "Common mistakes"}
    )
    assert session.state.concepts_covered == ["Common mistakes"]
    assert session.state.current_topic == "Binary Search"


def test_checkpoints_store_english_even_mid_sentence(dialogue_session):
    """A checkpoint cut mid-sentence must not freeze Arabic into the lesson state."""
    session = dialogue_session
    state = session.state
    state.language = "ar"
    state.topic_id = "binary-search"
    state.concepts_covered = []
    state.resume_checkpoint = None

    checkpoint = session.checkpoints._extract(
        state,
        "تمام، خلينا نشوف المثال ده. \u0641\u0643\u0631\u0629 \u0627\u0644\u062a\u0646\u0635\u064a\u0641",
        "interrupt",
    )
    assert checkpoint.last_concept == "The idea of halving", checkpoint.last_concept
    assert checkpoint.resume_instruction.startswith("Continue from 'The idea of halving'")
    assert checkpoint.resume_instruction.isascii()

    # plain Arabic with no catalogue wording keeps what was said (flagged, not guessed)
    other = session.checkpoints._extract(state, "\u062d\u0627\u062c\u0629 \u062a\u0627\u0646\u064a\u0629 \u062e\u0627\u0644\u0635", "interrupt")
    assert other.last_concept and other.resume_instruction


@pytest.mark.asyncio
async def test_the_plan_walks_in_arabic_while_the_state_stays_english():
    """One session, end to end: what is spoken vs what is stored."""
    topic = resolve("binary-search")
    metadata = {
        "topic_id": "binary-search",
        "topic_title": topic.title,
        "sections": [{"title": s.title, "goal": s.goal} for s in topic.sections],
    }
    dialogue = TutorDialogue.from_metadata(metadata, "ar")
    spoken = [dialogue.opening(), dialogue.respond("ماشي"), dialogue.respond("مش فاهم")]

    assert any("\u0600" <= ch <= "\u06ff" for ch in " ".join(spoken)), "the tutor must speak Arabic"
    assert not any(concept in " ".join(spoken) for concept in catalogue_concepts("binary-search")), (
        "the English plan must not be read aloud in an Arabic session"
    )

    state = VoiceSessionState(session_id="vs_en_store", student_id="s", language="ar",
                              topic_id="binary-search")
    for line in spoken:
        state.add_concept(canonicalise_concept(line, language="ar", topic_id="binary-search").canonical)
    assert all(concept.isascii() for concept in state.concepts_covered), state.concepts_covered


@pytest.mark.asyncio
async def test_the_offline_tutor_records_the_concept_in_english():
    """Teaching Arabic still fills the profile with the catalogue's concepts."""
    from app.providers.base import SessionConfig
    from app.providers.mock.providers import MockRealtimeProvider

    topic = resolve("binary-search")
    provider = MockRealtimeProvider()
    calls: list[tuple[str, dict]] = []

    async def handler(name, args):
        calls.append((name, args))

    provider.set_tool_handler(handler)
    await provider.start_session(
        SessionConfig(
            session_id="vs_mock_concepts",
            language="ar",
            system_instruction="teach",
            metadata={
                "topic_id": "binary-search",
                "topic_title": topic.title,
                "sections": [{"title": s.title, "goal": s.goal} for s in topic.sections],
            },
        )
    )
    await provider.send_text("start", trigger_response=True)   # opening: step 1
    await provider.send_text("\u0645\u0627\u0634\u064a", trigger_response=True)   # confirm: step 2

    positions = [args for name, args in calls if name == "update_lesson_position"]
    assert positions, "the tutor never reported its position"
    concepts = [p["last_concept"] for p in positions if p.get("last_concept")]
    assert concepts == ["The idea of halving"], concepts
    assert all(c.isascii() for c in concepts)
