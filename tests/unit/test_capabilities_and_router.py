"""Capability registry + router behaviour (§12, §13, §15, §16, §17)."""

from __future__ import annotations

import pytest

from app.providers.capabilities import (
    PROVIDER_CAPABILITIES,
    Capability,
    capability_matrix,
    providers_supporting,
)
from app.voice.provider_router import UnsupportedLanguageError, VoiceProviderRouter
from app.voice.state import SUPPORTED_LANGUAGES

ALL = ("gemini", "elevenlabs", "deepgram", "lerna")


def test_ten_languages_are_mandatory():
    assert SUPPORTED_LANGUAGES == ("en", "ar", "fr", "sw", "am", "ha", "so", "yo", "ig", "zu")
    assert len(SUPPORTED_LANGUAGES) == 10


def test_capabilities_are_separate_dimensions():
    gemini = PROVIDER_CAPABILITIES["gemini"]
    # Gemini can SPEAK Igbo but cannot hold a Live realtime conversation in it.
    assert gemini.supports(Capability.TTS, "ig")
    assert not gemini.supports(Capability.REALTIME, "ig")


def test_elevenlabs_has_igbo_stt_but_not_igbo_tts():
    el = PROVIDER_CAPABILITIES["elevenlabs"]
    assert el.supports(Capability.STT, "ig")
    assert not el.supports(Capability.TTS, "ig")
    assert not el.supports(Capability.TTS, "yo")


def test_deepgram_is_component_only():
    dg = PROVIDER_CAPABILITIES["deepgram"]
    assert dg.realtime == frozenset()
    assert dg.supports(Capability.STT, "en")
    assert not dg.supports(Capability.STT, "ig")
    assert not dg.supports(Capability.TTS, "zu")


def test_every_language_has_at_least_one_pipeline(settings):
    router = VoiceProviderRouter(settings=settings, available_providers=ALL)
    for language in SUPPORTED_LANGUAGES:
        plan = router.select_pipeline(language)
        assert plan is not None, language


def test_gemini_is_primary_for_the_nine_realtime_languages(settings):
    router = VoiceProviderRouter(settings=settings, available_providers=ALL)
    for language in ("en", "ar", "fr", "sw", "am", "ha", "so", "yo", "zu"):
        plan = router.select_pipeline(language)
        assert plan.pipeline.mode == "realtime"
        assert plan.pipeline.realtime == "gemini"


def test_igbo_routes_through_a_composed_pipeline(settings):
    """§15: no fabricated Gemini Live Igbo support."""
    router = VoiceProviderRouter(settings=settings, available_providers=ALL)
    plan = router.select_pipeline("ig")
    assert plan.pipeline.mode == "cascade"
    assert plan.pipeline.stt == "elevenlabs"  # only verified Igbo STT
    assert plan.pipeline.llm == "gemini"
    assert plan.pipeline.tts == "gemini"  # only verified Igbo TTS


def test_yoruba_falls_back_to_gemini_tts_not_elevenlabs(settings):
    router = VoiceProviderRouter(settings=settings, available_providers=ALL)
    cascades = [p for p in router.plan_pipelines("yo") if p.pipeline.mode == "cascade"]
    assert cascades
    assert all(p.pipeline.tts != "elevenlabs" for p in cascades)


def test_provider_mode_gemini_only(settings):
    settings.voice_provider_mode = "gemini_only"
    router = VoiceProviderRouter(settings=settings, available_providers=ALL)
    plan = router.select_pipeline("en")
    assert set(plan.providers) == {"gemini"}
    # Igbo has no Gemini-only pipeline at all -> explicit error, never a lie.
    with pytest.raises(UnsupportedLanguageError):
        router.select_pipeline("ig")


def test_elevenlabs_only_mode_cannot_serve_igbo(settings):
    settings.voice_provider_mode = "elevenlabs_only"
    router = VoiceProviderRouter(settings=settings, available_providers=ALL)
    with pytest.raises(UnsupportedLanguageError):
        router.select_pipeline("ig")


def test_unhealthy_provider_is_skipped(settings, health):
    router = VoiceProviderRouter(settings=settings, health=health, available_providers=ALL)
    for _ in range(settings.voice_circuit_breaker_threshold):
        health.record_failure("gemini", RuntimeError("boom"))
    plan = router.select_pipeline("en")
    assert plan.pipeline.mode == "cascade"
    assert plan.pipeline.llm == "lerna"
    assert "gemini" not in plan.providers


def test_fallback_chain_is_ordered_and_unique(settings):
    router = VoiceProviderRouter(settings=settings, available_providers=ALL)
    chain = router.fallback_chain("en", limit=4)
    signatures = [p.signature for p in chain]
    assert signatures[0] == "realtime:gemini"
    assert len(signatures) == len(set(signatures))


def test_capability_matrix_covers_all_languages_and_providers():
    matrix = capability_matrix()
    assert set(matrix) == set(SUPPORTED_LANGUAGES)
    for language, providers in matrix.items():
        assert {"gemini", "elevenlabs", "deepgram"} <= set(providers)


def test_providers_supporting_respects_priority():
    assert providers_supporting(Capability.STT, "en") == ["gemini", "elevenlabs", "deepgram"]
    assert providers_supporting(Capability.LLM, "ig") == ["gemini", "lerna"]
