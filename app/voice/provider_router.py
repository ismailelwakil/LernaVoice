"""VoiceProviderRouter (§16) — capability-aware, health-aware pipeline selection.

    language + required capability + provider health + priority
        => selected provider / composed pipeline
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable, Literal

from app.config import Settings, get_settings
from app.providers.capabilities import (
    DEFAULT_PRIORITY,
    MOCK_CAPABILITY,
    PROVIDER_CAPABILITIES,
    Capability,
    ProviderCapability,
)
from app.providers.health import ProviderHealthRegistry
from app.voice.state import ActivePipeline

Mode = Literal["realtime", "cascade", "any"]

MODE_TO_PROVIDERS: dict[str, tuple[str, ...]] = {
    "auto": DEFAULT_PRIORITY,
    "gemini_only": ("gemini",),
    # Backup-only modes still need a reasoning engine: ElevenLabs and Deepgram
    # provide no LLM, so LERNA's own model pool completes the cascade.
    "elevenlabs_only": ("elevenlabs", "lerna"),
    "deepgram_only": ("deepgram", "lerna"),
}


class UnsupportedLanguageError(Exception):
    def __init__(self, language: str, detail: str = ""):
        super().__init__(detail or f"No pipeline can serve language '{language}'")
        self.language = language


@dataclass(frozen=True)
class PipelinePlan:
    pipeline: ActivePipeline
    reason: str
    score: float

    @property
    def signature(self) -> str:
        return self.pipeline.signature()

    @property
    def providers(self) -> tuple[str, ...]:
        p = self.pipeline
        if p.mode == "realtime":
            return (p.realtime or "",)
        return (p.stt, p.llm, p.tts)

    def as_dict(self) -> dict:
        return {
            "mode": self.pipeline.mode,
            "realtime": self.pipeline.realtime,
            "stt": self.pipeline.stt,
            "llm": self.pipeline.llm,
            "tts": self.pipeline.tts,
            "signature": self.signature,
            "reason": self.reason,
        }


class VoiceProviderRouter:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        health: ProviderHealthRegistry | None = None,
        available_providers: Iterable[str] | None = None,
        capabilities: dict[str, ProviderCapability] | None = None,
    ):
        self.settings = settings or get_settings()
        self.health = health or ProviderHealthRegistry(
            failure_threshold=self.settings.voice_circuit_breaker_threshold,
            cooldown=self.settings.voice_circuit_breaker_cooldown,
        )
        self.capabilities = dict(capabilities or PROVIDER_CAPABILITIES)
        if available_providers is None:
            available = self.settings.configured_providers()
        else:
            available = set(available_providers)
        if "mock" in available and "mock" not in self.capabilities:
            self.capabilities["mock"] = MOCK_CAPABILITY
        self.available = available

    # ------------------------------------------------------------- ordering

    def _priority(self) -> tuple[str, ...]:
        base = list(MODE_TO_PROVIDERS.get(self.settings.voice_provider_mode, DEFAULT_PRIORITY))
        # Round 25: the LLM "brain" order is configurable (winner of the live benchmark
        # first, the other as fallback). Because a text-only provider such as openrouter
        # supports no realtime/tts role, ranking it first only reorders the LLM slot of
        # composed pipelines — native realtime (gemini) is unaffected.
        # The configurable LLM-brain order only applies in `auto` mode; restricted
        # modes (gemini_only / elevenlabs_only) keep exactly their own vendors.
        ordered: list[str] = []
        if self.settings.voice_provider_mode == "auto":
            llm_order = [p.strip() for p in (self.settings.llm_priority or "").split(",") if p.strip()]
            ordered = [p for p in llm_order if p in self.available or p in base]
        for p in base:
            if p not in ordered:
                ordered.append(p)
        # Truly-new providers (azure, openrouter) join as extras; the classic vendors
        # stay governed by the mode's base list so restricted modes keep their meaning.
        extras = [p for p in self.available if p not in ordered and p not in DEFAULT_PRIORITY]
        return tuple(ordered + extras)

    def _usable(self, provider: str, capability: Capability, language: str, *, respect_health: bool) -> bool:
        if provider not in self.available:
            return False
        cap = self.capabilities.get(provider)
        if cap is None or not cap.supports(capability, language):
            return False
        if respect_health and not self.health.is_available(provider):
            return False
        return True

    def _voice_priority(self) -> tuple[str, ...]:
        """Preferred spoken-voice order (round 30): azure, gemini, elevenlabs, …"""
        return tuple(p.strip() for p in (self.settings.voice_priority or "").split(",") if p.strip())

    def _rank(self, provider: str, priority: tuple[str, ...]) -> float:
        idx = priority.index(provider) if provider in priority else len(priority)
        return idx + self.health.penalty(provider) * 0.1

    # ------------------------------------------------------------- planning

    def plan_pipelines(
        self,
        language: str,
        *,
        mode: Mode = "any",
        exclude: Iterable[str] = (),
        respect_health: bool = True,
    ) -> list[PipelinePlan]:
        """All viable pipelines for `language`, best first."""
        excluded = set(exclude)
        priority = self._priority()
        plans: list[PipelinePlan] = []

        # 1) true realtime speech-to-speech providers
        if mode in ("realtime", "any"):
            for provider in priority:
                if not self._usable(provider, Capability.REALTIME, language, respect_health=respect_health):
                    continue
                pipeline = ActivePipeline(
                    mode="realtime", realtime=provider, stt=provider, llm=provider, tts=provider
                )
                if pipeline.signature() in excluded:
                    continue
                plans.append(
                    PipelinePlan(
                        pipeline=pipeline,
                        reason=f"{provider} supports native realtime conversation in '{language}'",
                        score=self._rank(provider, priority),
                    )
                )

        # 2) composed STT -> LLM -> TTS cascades
        if mode in ("cascade", "any"):
            stt_options = [p for p in priority if self._usable(p, Capability.STT, language, respect_health=respect_health)]
            tts_options = [p for p in priority if self._usable(p, Capability.TTS, language, respect_health=respect_health)]
            llm_options = [p for p in priority if self._usable(p, Capability.LLM, language, respect_health=respect_health)]
            for stt_p, llm_p, tts_p in product(stt_options, llm_options, tts_options):
                pipeline = ActivePipeline(mode="cascade", stt=stt_p, llm=llm_p, tts=tts_p, realtime=None)
                sig = pipeline.signature()
                if sig in excluded or any(p.signature == sig for p in plans):
                    continue
                # Round 30: a composed pipeline that speaks with the configured #1 voice
                # (Azure) is the PRIMARY plan — it outranks native realtime. Every other
                # cascade keeps the historical "below realtime" ranking, so health-based
                # failover ordering is unchanged.
                voice = self._voice_priority()
                # A strongly negative bias so the #1-voice cascade beats native realtime
                # regardless of where that vendor sits in the generic priority list.
                bias = -100.0 if (voice and tts_p == voice[0]) else 10.0
                score = (
                    bias
                    + self._rank(stt_p, priority)
                    + self._rank(llm_p, priority)
                    + self._rank(tts_p, priority)
                )
                plans.append(
                    PipelinePlan(
                        pipeline=pipeline,
                        reason=f"composed pipeline stt={stt_p}, llm={llm_p}, tts={tts_p} for '{language}'",
                        score=score,
                    )
                )

        plans.sort(key=lambda p: p.score)
        return plans

    def select_pipeline(
        self,
        language: str,
        *,
        mode: Mode = "any",
        exclude: Iterable[str] = (),
    ) -> PipelinePlan:
        """Best pipeline, or raise UnsupportedLanguageError."""
        plans = self.plan_pipelines(language, mode=mode, exclude=exclude, respect_health=True)
        if plans:
            return plans[0]
        # Everything healthy is excluded/unhealthy -> ignore health as last resort.
        plans = self.plan_pipelines(language, mode=mode, exclude=exclude, respect_health=False)
        if plans:
            return plans[0]
        raise UnsupportedLanguageError(
            language,
            f"No configured provider combination supports language '{language}' "
            f"(configured: {sorted(self.available) or 'none'})",
        )

    def fallback_chain(self, language: str, *, mode: Mode = "any", limit: int = 4) -> list[PipelinePlan]:
        return self.plan_pipelines(language, mode=mode, respect_health=True)[:limit]

    # ----------------------------------------------------------- bookkeeping

    def record_success(self, plan: PipelinePlan) -> None:
        for provider in set(plan.providers):
            if provider:
                self.health.record_success(provider)

    def record_failure(self, provider: str, error: Exception) -> None:
        self.health.record_failure(provider, error)

    def describe(self) -> dict:
        return {
            "mode": self.settings.voice_provider_mode,
            "available_providers": sorted(self.available),
            "priority": list(self._priority()),
            "health": self.health.snapshot(),
            "fallback_enabled": self.settings.voice_fallback_enabled,
        }
