"""Capability registry (§12).

Everything in this file was verified against official provider documentation on
2026-10-09.  Sources are recorded per block so the matrix can be re-audited.

IMPORTANT: STT support, TTS support and realtime-conversation support are three
SEPARATE capabilities.  A provider speaking a language does not imply it can
hold a realtime conversation in it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.voice.state import SUPPORTED_LANGUAGES


class Capability(str, Enum):
    REALTIME = "realtime"  # bidirectional speech-to-speech conversation
    STT = "stt"
    TTS = "tts"
    LLM = "llm"


# --------------------------------------------------------------------------- #
# GEMINI
# Live API (native audio, WebSocket, VAD + barge-in + tool calling) supports 99
# languages.  Verified list at
# https://ai.google.dev/gemini-api/docs/live-api/capabilities#supported-languages
# Of LERNA's ten: en ar fr sw am ha so yo zu are present.  **Igbo (ig) is NOT.**
# Gemini TTS (gemini-3.8-flash-tts, 130 languages) DOES include Igbo:
# https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-tts
# Gemini text models cover all ten languages.
# --------------------------------------------------------------------------- #
GEMINI_REALTIME_LANGUAGES = {"en", "ar", "fr", "sw", "am", "ha", "so", "yo", "zu"}
GEMINI_STT_LANGUAGES = set(GEMINI_REALTIME_LANGUAGES)  # Live API native audio input
GEMINI_TTS_LANGUAGES = set(SUPPORTED_LANGUAGES)  # gemini-3.8-flash-tts, incl. Igbo
GEMINI_LLM_LANGUAGES = set(SUPPORTED_LANGUAGES)

# --------------------------------------------------------------------------- #
# ELEVENLABS
# Scribe v2 Realtime STT: 90+ languages, ~150ms, WebSocket streaming, VAD.
# Includes Igbo (ibo), Yoruba (yor), Zulu (zul), Amharic, Hausa, Somali, Swahili.
# https://elevenlabs.io/docs/overview/capabilities/speech-to-text
# TTS eleven_v4 / eleven_v4_turbo: 90+ languages — the published list contains
# Hausa, Somali, Swahili, Zulu, Amharic, Arabic, French, English but **NOT Igbo
# and NOT Yoruba**: https://elevenlabs.io/docs/overview/models
# ElevenLabs is used here as STT + TTS components; the Agents platform is not
# used, so no `realtime` capability is claimed.
# --------------------------------------------------------------------------- #
ELEVENLABS_REALTIME_LANGUAGES: set[str] = set()
ELEVENLABS_STT_LANGUAGES = set(SUPPORTED_LANGUAGES)
ELEVENLABS_TTS_LANGUAGES = {"en", "ar", "fr", "sw", "am", "ha", "so", "zu"}
ELEVENLABS_LLM_LANGUAGES: set[str] = set()

# --------------------------------------------------------------------------- #
# DEEPGRAM
# Nova-3 / Flux streaming STT language list:
# https://developers.deepgram.com/docs/models-languages-overview
# Of LERNA's ten only en, ar, fr are officially listed.
# Aura / Aura-2 TTS supports en, es, de, fr, nl, it, ja only:
# https://developers.deepgram.com/docs/tts-models
# Deepgram is therefore a *component* provider (mainly STT), never a complete
# voice stack.
# --------------------------------------------------------------------------- #
DEEPGRAM_REALTIME_LANGUAGES: set[str] = set()
DEEPGRAM_STT_LANGUAGES = {"en", "ar", "fr"}
DEEPGRAM_TTS_LANGUAGES = {"en", "fr"}
DEEPGRAM_LLM_LANGUAGES: set[str] = set()

# --------------------------------------------------------------------------- #
# LERNA (the existing Academic OS model pool)
# Not a voice vendor: it is the platform's own multi-provider text LLM pool
# (Gemini / OpenAI / Anthropic / Groq via infrastructure/llms/providers.py).
# Exposing it as an LLM component means a cascade can keep tutoring when the
# Gemini *voice* path is down, and satisfies the "reuse LERNA's AI" rule (§68).
# --------------------------------------------------------------------------- #
LERNA_LLM_LANGUAGES = set(SUPPORTED_LANGUAGES)


@dataclass(frozen=True)
class ProviderCapability:
    name: str
    realtime: frozenset[str] = field(default_factory=frozenset)
    stt: frozenset[str] = field(default_factory=frozenset)
    tts: frozenset[str] = field(default_factory=frozenset)
    llm: frozenset[str] = field(default_factory=frozenset)
    streaming_stt: bool = False
    streaming_tts: bool = False
    turn_detection: bool = False
    native_interruption: bool = False
    tool_calling: bool = False
    notes: str = ""

    def languages_for(self, capability: Capability) -> frozenset[str]:
        return getattr(self, capability.value)

    def supports(self, capability: Capability, language: str) -> bool:
        return language in self.languages_for(capability)


PROVIDER_CAPABILITIES: dict[str, ProviderCapability] = {
    "gemini": ProviderCapability(
        name="gemini",
        realtime=frozenset(GEMINI_REALTIME_LANGUAGES),
        stt=frozenset(GEMINI_STT_LANGUAGES),
        tts=frozenset(GEMINI_TTS_LANGUAGES),
        llm=frozenset(GEMINI_LLM_LANGUAGES),
        streaming_stt=True,
        streaming_tts=True,
        turn_detection=True,
        native_interruption=True,
        tool_calling=True,
        notes=(
            "Live API native audio: streaming WS, server VAD, barge-in, function calling. "
            "Igbo is NOT supported by Live API; Gemini Flash TTS does cover Igbo."
        ),
    ),
    "elevenlabs": ProviderCapability(
        name="elevenlabs",
        realtime=frozenset(ELEVENLABS_REALTIME_LANGUAGES),
        stt=frozenset(ELEVENLABS_STT_LANGUAGES),
        tts=frozenset(ELEVENLABS_TTS_LANGUAGES),
        llm=frozenset(ELEVENLABS_LLM_LANGUAGES),
        streaming_stt=True,
        streaming_tts=True,
        turn_detection=True,  # Scribe v2 Realtime VAD segmentation
        native_interruption=False,
        tool_calling=False,
        notes=(
            "Scribe v2 Realtime STT (90+ langs incl. Igbo/Yoruba) and v4-turbo streaming TTS "
            "(no Igbo, no Yoruba). Used as components inside a cascade."
        ),
    ),
    "lerna": ProviderCapability(
        name="lerna",
        llm=frozenset(LERNA_LLM_LANGUAGES),
        notes=(
            "LERNA's existing LLM pool, reached in-process through the Academic OS engine. "
            "Text reasoning only - no speech capability of its own."
        ),
    ),
    "deepgram": ProviderCapability(
        name="deepgram",
        realtime=frozenset(DEEPGRAM_REALTIME_LANGUAGES),
        stt=frozenset(DEEPGRAM_STT_LANGUAGES),
        tts=frozenset(DEEPGRAM_TTS_LANGUAGES),
        llm=frozenset(DEEPGRAM_LLM_LANGUAGES),
        streaming_stt=True,
        streaming_tts=True,
        turn_detection=True,  # Flux model-native turn detection
        native_interruption=False,
        tool_calling=False,
        notes=(
            "Nova-3/Flux streaming STT (en/ar/fr of LERNA's ten) and Aura-2 TTS (en/fr). "
            "Component provider only."
        ),
    ),
}

# --------------------------------------------------------------------------- #
# AZURE AI SPEECH
# Free tier F0: 0.5M characters/month neural TTS (per Microsoft's pricing page and
# quota docs, verified 2026-10-11).  Voices are the same catalogue the browser's
# "Natural" voices come from.  Present of LERNA's ten: en ar fr sw am so zu —
# **no Hausa, no Yoruba, no Igbo**.
# --------------------------------------------------------------------------- #
AZURE_TTS_LANGUAGES = {"en", "ar", "fr", "sw", "am", "so", "zu"}

PROVIDER_CAPABILITIES["azure"] = ProviderCapability(
        name="azure",
        realtime=frozenset(),
        stt=frozenset(),
        tts=frozenset(AZURE_TTS_LANGUAGES),
        llm=frozenset(),
        streaming_stt=False,
        streaming_tts=False,
        turn_detection=False,
        native_interruption=False,
        tool_calling=False,
        notes=(
            "Azure AI Speech neural TTS (free F0 tier, 0.5M chars/month). Same voice "
            "catalogue as the browser's 'Natural' voices. No Hausa/Yoruba/Igbo."
        ),
)

# OpenRouter (round 25): an OpenAI-compatible LLM gateway. Text reasoning only —
# speech comes from a TTS vendor (Azure) in a composed pipeline.
PROVIDER_CAPABILITIES["openrouter"] = ProviderCapability(
    name="openrouter",
    realtime=frozenset(),
    stt=frozenset(),
    tts=frozenset(),
    llm=frozenset(SUPPORTED_LANGUAGES),
    streaming_stt=False,
    streaming_tts=False,
    turn_detection=False,
    native_interruption=False,
    tool_calling=False,
    notes=(
        "OpenAI-compatible LLM gateway (any hosted model). Text reasoning only; "
        "paired with Azure TTS in a cascade so OpenRouter writes and Azure speaks."
    ),
)

# Fish Audio (round 27): backup TTS voice. Free `s2.1-pro-free` model auto-detects
# the input language (83 languages, Arabic included). Only the documented subset of
# LERNA's ten is claimed here (en ar fr sw); the rest are unverified, so the router
# never sends a mandatory language to an unproven voice.
PROVIDER_CAPABILITIES["fish"] = ProviderCapability(
    name="fish",
    realtime=frozenset(),
    stt=frozenset(),
    tts=frozenset({"en", "ar", "fr", "sw"}),
    llm=frozenset(),
    streaming_stt=False,
    streaming_tts=False,
    turn_detection=False,
    native_interruption=False,
    tool_calling=False,
    notes=(
        "Fish Audio neural TTS (free s2.1-pro-free tier, auto language detection). "
        "Backup speaker behind Azure. Documented languages only: en ar fr sw."
    ),
)

# Mock vendor used by the test-suite; never selected in production routing.
MOCK_CAPABILITY = ProviderCapability(
    name="mock",
    realtime=frozenset(SUPPORTED_LANGUAGES),
    stt=frozenset(SUPPORTED_LANGUAGES),
    tts=frozenset(SUPPORTED_LANGUAGES),
    llm=frozenset(SUPPORTED_LANGUAGES),
    streaming_stt=True,
    streaming_tts=True,
    turn_detection=True,
    native_interruption=True,
    tool_calling=True,
    notes="Deterministic in-memory provider for automated tests only.",
)

DEFAULT_PRIORITY: tuple[str, ...] = ("gemini", "elevenlabs", "deepgram", "lerna")


def providers_supporting(capability: Capability, language: str, *, include_mock: bool = False) -> list[str]:
    """Priority-ordered vendors able to serve `capability` in `language`."""
    registry = dict(PROVIDER_CAPABILITIES)
    if include_mock:
        registry["mock"] = MOCK_CAPABILITY
    order = list(DEFAULT_PRIORITY) + (["mock"] if include_mock else [])
    return [p for p in order if p in registry and registry[p].supports(capability, language)]


def capability_matrix() -> dict[str, dict[str, dict[str, bool]]]:
    """language -> provider -> {capability: bool}; used by docs and /health/providers."""
    out: dict[str, dict[str, dict[str, bool]]] = {}
    for lang in SUPPORTED_LANGUAGES:
        out[lang] = {}
        for pname, cap in PROVIDER_CAPABILITIES.items():
            out[lang][pname] = {c.value: cap.supports(c, lang) for c in Capability}
    return out
