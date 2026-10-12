"""Provider factory (§7) — turns a routing decision into live objects.

This is the ONLY place allowed to map a vendor name to a concrete class.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from app.config import Settings, get_settings
from app.providers.base import (
    LLMProvider,
    ProviderUnsupportedError,
    RealtimeVoiceProvider,
    SpeechToTextProvider,
    TextToSpeechProvider,
)
from app.providers.cascade import CascadePipelineProvider
from app.voice.state import ActivePipeline


class ProviderFactory:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._realtime: dict[str, Callable[[], RealtimeVoiceProvider]] = {}
        self._stt: dict[str, Callable[[], SpeechToTextProvider]] = {}
        self._tts: dict[str, Callable[[], TextToSpeechProvider]] = {}
        self._llm: dict[str, Callable[[], LLMProvider]] = {}
        self._register_builtin()

    # -------------------------------------------------------------- registry

    def _register_builtin(self) -> None:
        s = self.settings

        def gemini_live() -> RealtimeVoiceProvider:
            from app.providers.gemini.live import GeminiLiveProvider

            return GeminiLiveProvider(s)

        def gemini_llm() -> LLMProvider:
            from app.providers.gemini.llm import GeminiLLMProvider

            return GeminiLLMProvider(s)

        def gemini_tts() -> TextToSpeechProvider:
            from app.providers.gemini.tts import GeminiTTSProvider

            return GeminiTTSProvider(s)

        def elevenlabs_stt() -> SpeechToTextProvider:
            from app.providers.elevenlabs.stt import ElevenLabsSTTProvider

            return ElevenLabsSTTProvider(s)

        def elevenlabs_tts() -> TextToSpeechProvider:
            from app.providers.elevenlabs.tts import ElevenLabsTTSProvider

            return ElevenLabsTTSProvider(s)

        def deepgram_stt() -> SpeechToTextProvider:
            from app.providers.deepgram.stt import DeepgramSTTProvider

            return DeepgramSTTProvider(s)

        def deepgram_tts() -> TextToSpeechProvider:
            from app.providers.deepgram.tts import DeepgramTTSProvider

            return DeepgramTTSProvider(s)

        def lerna_llm() -> LLMProvider:
            from app.providers.lerna.llm import LernaLLMProvider

            return LernaLLMProvider()

        def openrouter_llm() -> LLMProvider:
            from app.providers.openrouter.llm import OpenRouterLLMProvider

            return OpenRouterLLMProvider(s)

        self._realtime["gemini"] = gemini_live
        self._llm["lerna"] = lerna_llm
        self._llm["gemini"] = gemini_llm
        if s.openrouter_configured:
            self._llm["openrouter"] = openrouter_llm
        self._tts["gemini"] = gemini_tts
        # Gemini Live doubles as its own STT inside a realtime session; as a
        # standalone cascade component it is not exposed (use EL/DG instead).
        def azure_tts() -> TextToSpeechProvider:
            from app.providers.azure.tts import AzureTTSProvider

            return AzureTTSProvider(s)

        self._tts["azure"] = azure_tts

        def fish_tts() -> TextToSpeechProvider:
            from app.providers.fish.tts import FishAudioTTSProvider

            return FishAudioTTSProvider(s)

        self._tts["fish"] = fish_tts
        self._stt["elevenlabs"] = elevenlabs_stt
        self._tts["elevenlabs"] = elevenlabs_tts
        self._stt["deepgram"] = deepgram_stt
        self._tts["deepgram"] = deepgram_tts

        if getattr(self.settings, "voice_enable_mock_providers", False):
            self.register_mocks()
            self.register_vendor_mocks()

    def register_vendor_mocks(self) -> None:
        """Demo/dev mode: serve the REAL vendor names with mock implementations
        so routing, cascades and failover can be exercised with no credentials.
        Never enabled unless VOICE_ENABLE_MOCK_PROVIDERS=true."""
        from app.providers.mock.providers import (
            MockLLMProvider,
            MockRealtimeProvider,
            MockSTTProvider,
            MockTTSProvider,
        )

        self._realtime["gemini"] = lambda: MockRealtimeProvider("gemini")
        self._llm["gemini"] = lambda: MockLLMProvider("gemini")
        self._tts["gemini"] = lambda: MockTTSProvider("gemini")
        self._stt["elevenlabs"] = lambda: MockSTTProvider("elevenlabs")
        self._tts["elevenlabs"] = lambda: MockTTSProvider("elevenlabs")
        self._tts["fish"] = lambda: MockTTSProvider("fish")
        self._stt["deepgram"] = lambda: MockSTTProvider("deepgram")
        self._tts["deepgram"] = lambda: MockTTSProvider("deepgram")
        self._llm["lerna"] = lambda: MockLLMProvider("lerna")

    def register_mocks(self) -> None:
        from app.providers.mock.providers import (
            MockLLMProvider,
            MockRealtimeProvider,
            MockSTTProvider,
            MockTTSProvider,
        )

        self._realtime["mock"] = lambda: MockRealtimeProvider("mock")
        self._stt["mock"] = lambda: MockSTTProvider("mock")
        self._tts["mock"] = lambda: MockTTSProvider("mock")
        self._llm["mock"] = lambda: MockLLMProvider("mock")

    def register(self, role: str, vendor: str, builder: Callable[[], Any]) -> None:
        target = {"realtime": self._realtime, "stt": self._stt, "tts": self._tts, "llm": self._llm}[role]
        target[vendor] = builder

    def available(self, role: str) -> list[str]:
        return sorted({"realtime": self._realtime, "stt": self._stt, "tts": self._tts, "llm": self._llm}[role])

    # ---------------------------------------------------------------- builds

    def build_realtime(self, vendor: str) -> RealtimeVoiceProvider:
        builder = self._realtime.get(vendor)
        if builder is None:
            raise ProviderUnsupportedError(f"no realtime provider registered for '{vendor}'", provider=vendor)
        return builder()

    def build_stt(self, vendor: str) -> SpeechToTextProvider:
        builder = self._stt.get(vendor)
        if builder is None:
            raise ProviderUnsupportedError(f"no STT provider registered for '{vendor}'", provider=vendor)
        return builder()

    def build_tts(self, vendor: str) -> TextToSpeechProvider:
        builder = self._tts.get(vendor)
        if builder is None:
            raise ProviderUnsupportedError(f"no TTS provider registered for '{vendor}'", provider=vendor)
        return builder()

    def build_llm(self, vendor: str) -> LLMProvider:
        builder = self._llm.get(vendor)
        if builder is None:
            raise ProviderUnsupportedError(f"no LLM provider registered for '{vendor}'", provider=vendor)
        return builder()

    def build_pipeline(self, pipeline: ActivePipeline) -> RealtimeVoiceProvider:
        """One call, one conversation object — whatever the composition is."""
        if pipeline.mode == "realtime":
            provider: RealtimeVoiceProvider = self.build_realtime(pipeline.realtime or pipeline.llm)
        else:
            provider = CascadePipelineProvider(
                stt=self.build_stt(pipeline.stt),
                llm=self.build_llm(pipeline.llm),
                tts=self.build_tts(pipeline.tts),
                name=pipeline.signature(),
            )
        # An offline demo can still *sound* like a person: the dialogue stays
        # local, the voice comes from a real TTS vendor (VOICE_DEMO_VOICE).
        from app.voice.demo_voice import attach_demo_voice

        attach_demo_voice(provider, self, self.settings)
        # Round 27 — voice failover: if the active voice fails before speaking
        # (e.g. Azure is down), the cascade tries the other configured voices in
        # order. Fish Audio sits right behind Azure as the backup speaker.
        if isinstance(provider, CascadePipelineProvider):
            provider.tts_fallbacks = self._tts_failover(provider.tts)
        return provider

    #: Voice failover order (round 30) — Azure primary, Gemini second, ElevenLabs third.
    TTS_FAILOVER_ORDER = ("azure", "gemini", "elevenlabs", "fish", "deepgram")

    def _tts_failover(self, primary: TextToSpeechProvider) -> list[TextToSpeechProvider]:
        """Backup voices for `primary`, in failover order, configured ones only."""
        primary_name = getattr(primary, "provider_name", None)
        if self.settings.voice_enable_mock_providers:
            configured = set(self._tts) | {"azure"}  # demo mode: every registered voice
        else:
            configured = self.settings.configured_providers() | {"azure"}
        fallbacks: list[TextToSpeechProvider] = []
        for vendor in self.TTS_FAILOVER_ORDER:
            if vendor == primary_name or vendor not in self._tts or vendor not in configured:
                continue
            try:
                fallbacks.append(self.build_tts(vendor))
            except Exception:  # noqa: BLE001
                continue
        return fallbacks


_factory: ProviderFactory | None = None


def get_factory(settings: Settings | None = None) -> ProviderFactory:
    global _factory
    if _factory is None:
        _factory = ProviderFactory(settings)
    return _factory


def set_factory(factory: ProviderFactory | None) -> None:
    global _factory
    _factory = factory
