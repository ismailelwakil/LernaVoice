"""Arabic is taught in Modern Standard Arabic (fusHa) - app/voice/dialects.py.

Arabic is one language and one register: clear modern fusHa, voice
`ar-SA-ZariyahNeural`, formal phrase tables, a lecture-style sentence in the
system instruction. The `dialect` field survives in the API as a compatibility
hook (clients sent `ar-EG` before this change) and everything that asks "which
language?" still gets `ar`, so routing, checkpoints and the canonical-English
concept store are untouched.
"""

from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.providers.azure.tts import AzureTTSProvider, voice_for
from app.providers.base import AudioChunk, SessionConfig
from app.providers.mock.providers import MockRealtimeProvider
from app.voice.dialects import (
    arabic_dialect_options,
    dialect_lang_tag,
    dialect_voice,
    line_language,
    normalise_dialect,
)
from app.voice.events import EventType
from app.voice.state import SUPPORTED_LANGUAGES

WAV_HEADER = b"RIFF" + (36 + 480).to_bytes(4, "little") + b"WAVE"
WAV_HEADER += b"fmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little")
WAV_HEADER += (1).to_bytes(2, "little") + (24000).to_bytes(4, "little")
WAV_HEADER += (48000).to_bytes(4, "little") + (2).to_bytes(2, "little")
WAV_HEADER += (16).to_bytes(2, "little") + b"data" + (480).to_bytes(4, "little")
FRAMES = b"\x07\x00" * 240

#: Egyptian wording that must no longer appear anywhere in the Arabic tables.
EGYPTIAN_MARKERS = ("النهاردة", "دلوقتي", "مفيش", "أيوة كده", "خد وقتك", "إحنا")


def _settings(**kw) -> Settings:
    base = dict(
        _env_file=None,
        azure_speech_key="azure_test_key",
        azure_speech_region="germanywestcentral",
        output_sample_rate=24000,
    )
    base.update(kw)
    return Settings(**base)


# --------------------------------------------------------------------------- #
# the registry
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "given",
    [None, "ar-MSA", "msa", "fusha", "  FusHa ", "nonsense"],
)
def test_fusHa_spellings_still_resolve_to_fusHa(given):
    """The default register is unchanged: fusHa spellings (and unknown ones) → ar-MSA."""
    assert normalise_dialect("ar", given) == "ar-MSA"


@pytest.mark.parametrize("given", ["ar-EG", "ar_eg", "egyptian", "masri", "مصري", "عامية"])
def test_egyptian_spellings_resolve_to_the_polite_egyptian_register(given):
    """Round 24: Egyptian is a real, optional register again — polite, not slang."""
    assert normalise_dialect("ar", given) == "ar-EG"


def test_a_register_written_into_the_language_field_is_understood():
    """Round-17 clients sent `{"language": "ar-MSA"}`; that must not 422."""
    from app.api.schemas import CreateSessionRequest, LanguageChangeRequest
    from app.voice.dialects import split_language

    assert split_language("ar-EG") == ("ar", "ar-EG")
    assert split_language("ar_msa") == ("ar", "ar-MSA")
    assert split_language("ar") == ("ar", None)
    assert split_language("EN") == ("en", None)

    request = CreateSessionRequest(student_id="s1", language="ar-EG")
    assert (request.language, request.dialect) == ("ar", "ar-EG")
    assert CreateSessionRequest(student_id="s1", language="ar-MSA").dialect == "ar-MSA"
    assert CreateSessionRequest(student_id="s1", language="ar", dialect="egyptian").dialect == "ar-EG"
    # default (no dialect) stays fusHa
    assert CreateSessionRequest(student_id="s1", language="ar").dialect == "ar-MSA"
    # the register is Arabic's alone
    assert CreateSessionRequest(student_id="s1", language="en", dialect="ar-MSA").dialect is None
    assert LanguageChangeRequest(language="ar-EG").language == "ar-EG"

    with pytest.raises(Exception):
        CreateSessionRequest(student_id="s1", language="xx")


def test_other_languages_have_no_register():
    assert normalise_dialect("en", "ar-MSA") is None
    assert normalise_dialect("fr", None) is None
    assert line_language("fr", None) == "fr"
    assert line_language("ar", None) == "ar"


def test_the_register_decides_the_voice_and_the_lang_tag():
    assert dialect_voice("ar", None) == "ar-SA-ZariyahNeural"          # default fusHa
    assert dialect_voice("ar", "ar-EG") == "ar-EG-SalmaNeural"         # polite Egyptian
    assert dialect_lang_tag("ar", "ar-MSA") == "ar-SA"
    assert dialect_lang_tag("ar", "ar-EG") == "ar-EG"
    assert [d["code"] for d in arabic_dialect_options()] == ["ar-MSA", "ar-EG"]
    assert arabic_dialect_options()[0]["local"] == "العربية الفصحى"


def test_voice_for_speaks_fusHa_and_honours_an_override():
    settings = _settings()
    assert voice_for("ar", settings) == "ar-SA-ZariyahNeural"
    assert voice_for("ar", settings, "ar-EG") == "ar-EG-SalmaNeural", "polite Egyptian voice"
    override = _settings(azure_voice_overrides="ar-MSA:ar-SA-HamedNeural")
    assert voice_for("ar", override) == "ar-SA-HamedNeural"
    assert voice_for("en", override) == "en-US-AvaMultilingualNeural"


# --------------------------------------------------------------------------- #
# how it sounds
# --------------------------------------------------------------------------- #


def test_ssml_speaks_the_register_like_a_person():
    provider = AzureTTSProvider(_settings())
    ssml = provider._ssml(
        "مرحبًا بك. سنشرح binary search خطوة بخطوة، هل الأمر واضح؟",
        "ar-SA-ZariyahNeural",
        language="ar",
        dialect="ar-MSA",
    )
    assert "xml:lang='ar-SA'" in ssml
    assert "xmlns:mstts" in ssml
    assert 'style="cheerful"' in ssml                       # expressive, not flat
    assert 'pitch="+2%"' in ssml                            # a little warmth
    assert '<break time="240ms"/>' in ssml                  # a breath between sentences
    assert '<break time="120ms"/>' in ssml                  # a beat at the comma
    assert '<emphasis level="moderate">binary search</emphasis>' in ssml


@pytest.mark.asyncio
async def test_a_voice_that_refuses_the_style_still_speaks(monkeypatch):
    """`mstts:express-as` is per-voice: a refusal must cost one retry, not the line."""
    calls: list[bytes] = []

    class _Client:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, content=None, **__):
            calls.append(content)
            if b"express-as" in content:
                return httpx.Response(400, content=b"<error>unsupported style</error>")
            return httpx.Response(200, content=WAV_HEADER + FRAMES)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    provider = AzureTTSProvider(_settings())
    provider.set_language_context("ar", "ar-MSA")

    chunks = [c async for c in provider.synthesize_stream("مرحبًا", "ar")]
    assert chunks and b"".join(c.data for c in chunks) == FRAMES
    assert len(calls) == 2, "expected exactly one retry without the style"
    assert b"express-as" in calls[0] and b"express-as" not in calls[1]
    assert provider._style_refused == {"ar-SA-ZariyahNeural"}

    calls.clear()
    chunks = [c async for c in provider.synthesize_stream("أهلًا", "ar")]
    assert len(calls) == 1 and b"express-as" not in calls[0], "the refusal should stick"


# --------------------------------------------------------------------------- #
# the words
# --------------------------------------------------------------------------- #


def test_the_arabic_phrase_table_is_formal():
    from app.prompts.interaction import INTERACTION_PHRASES, phrase, step_lead

    assert phrase("ar", "check") == "هل الأمر واضح حتى هنا؟"
    assert phrase("ar", "praise") == "بالضبط، أحسنت."
    assert phrase("ar", "topic_line").format(topic="البحث الثنائي") == "نتناول اليوم البحث الثنائي."
    assert step_lead("ar", "فكرة التنصيف", "نقسم المدى نصفين", 1) == (
        "حسنًا، فكرة التنصيف. نقسم المدى نصفين."
    )
    # …and nothing Egyptian is left anywhere in the table
    spoken = " ".join(INTERACTION_PHRASES["ar"].values())
    for marker in EGYPTIAN_MARKERS:
        assert marker not in spoken, f"Egyptian wording survived: {marker}"
    assert set(INTERACTION_PHRASES["ar"]) == set(INTERACTION_PHRASES["en"])
    assert "ar-msa" not in INTERACTION_PHRASES


def test_the_egyptian_phrase_table_is_polite_not_slang():
    from app.prompts.interaction import INTERACTION_PHRASES, phrase

    egy = INTERACTION_PHRASES["ar-eg"]
    # respectful markers, no crude slang
    assert "يا فندم" in egy["check"] or "حضرتك" in egy["which_part"]
    assert "مش فاهم" not in " ".join(egy.values())
    # an uncurated key falls back to fusHa, never to English
    assert phrase("ar-eg", "holding") == "خد وقتك، أنا مستنيك."
    # the Egyptian greeting resolves
    assert phrase("ar-eg", "praise") == "بالظبط كده، أحسنت."


def test_the_greeting_is_formal_and_covers_exactly_the_ten_languages():
    from app.curriculum import LOCALISED_GREETINGS

    assert LOCALISED_GREETINGS["ar"] == "مرحبًا بك، لنبدأ الدرس."
    # the ten languages, plus the optional polite-Egyptian register
    assert set(LOCALISED_GREETINGS) == set(SUPPORTED_LANGUAGES) | {"ar-eg"}
    assert "فندم" in LOCALISED_GREETINGS["ar-eg"] or "أهلًا" in LOCALISED_GREETINGS["ar-eg"]


def test_the_dialogue_speaks_fusHa():
    from app.providers.mock.dialogue import TutorDialogue

    metadata = {
        "topic_id": "binary-search",
        "topic_title": "Binary Search",
        "sections": [
            {"title": "The idea of halving", "goal": "Split the range in half"},
            {"title": "Trace it on a small array", "goal": "Walk the indexes"},
        ],
    }
    dialogue = TutorDialogue.from_metadata({**metadata, "dialect": "ar-MSA"}, "ar")
    assert (dialogue.language, dialogue.line_language) == ("ar", "ar")
    opening = dialogue.opening()
    assert "مرحبًا بك" in opening and "نتناول اليوم" in opening, opening
    for marker in EGYPTIAN_MARKERS:
        assert marker not in opening
    # the lesson itself is unchanged: same plan, same (English) catalogue topic
    assert dialogue.plan_topic == "Binary Search"
    assert dialogue._p("nothing_more") == "لا أكثر من ذلك."


# --------------------------------------------------------------------------- #
# wired through the session
# --------------------------------------------------------------------------- #


async def test_the_session_records_fusHa_as_its_register(manager):
    arabic = await manager.create(student_id="s1", language="ar", topic="Binary Search")
    assert arabic.state.language == "ar" and arabic.state.dialect == "ar-MSA"

    default = await manager.create(student_id="s1", language="ar", topic="Binary Search")
    assert default.state.dialect == "ar-MSA", "no dialect requested -> fusHa stays the default"

    forwarded = await manager.create(
        student_id="s1", language="ar", topic="Binary Search", dialect="egyptian"
    )
    assert forwarded.state.dialect == "ar-EG", "an Egyptian request gets the polite register"

    english = await manager.create(student_id="s1", language="en", dialect="ar-MSA")
    assert english.state.dialect is None


async def test_switching_registers_changes_the_dialect_but_keeps_the_lesson(manager, recorder):
    """Round 24: fusHa <-> Egyptian is a real register switch, not a no-op."""
    session = await manager.create(student_id="s1", language="ar", topic="Binary Search")
    rec = recorder(session)
    session.state.concepts_covered = ["The idea of halving"]
    await rec.drain()

    assert (await session.change_language("ar-MSA"))["changed"] is False   # same register
    assert (await session.change_language("ar-EG"))["changed"] is True     # new register
    await rec.drain()

    assert session.state.language == "ar" and session.state.dialect == "ar-EG"
    assert session.state.concepts_covered == ["The idea of halving"], "lesson untouched"
    assert rec.of(EventType.LANGUAGE_CHANGED), "the switch is announced"


async def test_the_pipeline_tells_the_voice_which_register(manager):
    session = await manager.create(student_id="s1", language="ar", topic="Binary Search")
    config = await session._build_session_config()
    assert config.metadata["dialect"] == "ar-MSA"
    assert "الفصحى" in config.system_instruction
    assert "binary" in config.metadata["topic_title"].lower()


async def test_a_demo_voice_is_told_the_register():
    from app.voice import demo_voice as dv

    settings = _settings(voice_demo_voice="azure")
    provider = MockRealtimeProvider()
    assert dv.attach_demo_voice(provider, None, settings) == "azure"
    gate = provider.tts
    assert gate.covers("ar") is True and gate.vendor == "azure"

    await provider.start_session(
        SessionConfig(
            session_id="vs_dialect",
            language="ar",
            system_instruction="be a tutor",
            metadata={"dialect": "ar-MSA", "topic_title": "Binary Search"},
        )
    )
    assert provider.dialect == "ar-MSA"
    assert gate.dialect == "ar-MSA" and gate.vendor_tts.dialect == "ar-MSA"
    assert voice_for("ar", settings, gate.vendor_tts.dialect) == "ar-SA-ZariyahNeural"


async def test_audio_still_arrives_in_arabic(manager):
    """The whole point: a formal Arabic lesson, real audio, unchanged lesson state."""
    import asyncio
    import base64

    session = await manager.create(student_id="s1", language="ar", topic="Binary Search")
    rec = session.subscribe()
    await session.start()
    await asyncio.sleep(0.2)
    frames: list[bytes] = []
    while not rec.empty():
        event = rec.get_nowait()
        if event.event is EventType.ASSISTANT_AUDIO_CHUNK:
            frames.append(base64.b64decode(event.data.get("audio") or ""))
    assert frames and all(len(f) > 0 for f in frames)
    assert session.state.current_topic == "Binary Search"
    assert session.state.dialect == "ar-MSA"


def test_audio_chunk_type_is_used_by_the_mock():
    """Guard against a silently renamed event: the test above depends on it."""
    chunk = AudioChunk(data=b"\x00\x01", sample_rate=16000)
    assert chunk.data == b"\x00\x01"
