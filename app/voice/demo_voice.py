"""A real voice for the offline demo.

The conversation can run on the offline dialogue policy (no vendor LLM, no vendor
STT, no paid credentials) while the *speech* still comes from a real
text-to-speech vendor. That is the difference between "a robot reading a
checklist" and "a tutor talking": the words are the same, the voice is not.

Enabled with ``VOICE_DEMO_VOICE``:

  * ``auto`` (default) \u2014 Azure Speech when ``AZURE_SPEECH_KEY`` is set (0.5M
    characters/month free, ~50x ElevenLabs' free credits), otherwise ElevenLabs,
    otherwise the synthetic demo voice.
  * ``azure`` / ``elevenlabs`` \u2014 require that vendor (a session falls back to the
    synthetic voice and says so in the event stream if the vendor fails).
  * ``off`` \u2014 never call a vendor from the mock path.

The attach happens in :meth:`ProviderFactory.build_pipeline`, so it also applies
after a failover to a mock pipeline mid-lesson. Nothing here is used when the
pipeline is a real realtime vendor: that vendor already *is* the voice.
"""

from __future__ import annotations

import logging

from app.config import Settings

logger = logging.getLogger(__name__)

DEMO_VOICE_MODES = ("auto", "off", "elevenlabs", "azure")


def azure_configured(settings: Settings) -> bool:
    return bool(getattr(settings, "azure_speech_key", None) and getattr(settings, "azure_speech_region", None))


def demo_voice_vendor(settings: Settings) -> str | None:
    """Which vendor should voice the offline demo, if any.

    `auto` prefers Azure: its free tier is 0.5M characters/month against
    ElevenLabs' 10 000 credits, so it buys ~50x the talking time.
    """
    mode = (getattr(settings, "voice_demo_voice", "auto") or "auto").lower()
    if mode == "off":
        return None
    if mode == "elevenlabs":
        return "elevenlabs" if settings.elevenlabs_configured else None
    if mode == "azure":
        return "azure" if azure_configured(settings) else None
    # auto
    if azure_configured(settings):
        return "azure"
    if settings.elevenlabs_configured:
        return "elevenlabs"
    return None


def demo_voice_label(settings: Settings) -> str | None:
    """`elevenlabs:eleven_v4_turbo` — operational shape for /health, no secrets."""
    vendor = demo_voice_vendor(settings)
    if vendor is None:
        return None
    if vendor == "elevenlabs":
        return f"elevenlabs:{settings.elevenlabs_tts_model}"
    if vendor == "azure":
        from app.providers.azure.tts import voice_for

        return f"azure:{voice_for('ar', settings)}"
    return vendor


def vendor_covers_language(vendor: str, language: str, settings: Settings) -> bool:
    """Can this vendor actually speak `language`?

    Both vendors have gaps: Azure has no Hausa/Yoruba/Igbo voice, ElevenLabs has
    neither Igbo nor Yoruba. Asking a vendor for a language it does not have
    raises `unsupported`, and on a *cascade* that looks to the router like a
    provider failure: it fails the whole pipeline over mid-turn and the student
    gets silence. So the demo voice has to know its limits before it speaks.
    """
    language = (language or "").lower()
    if vendor == "azure":
        from app.providers.azure.tts import voice_for

        return voice_for(language, settings) is not None
    if vendor == "elevenlabs":
        from app.providers.capabilities import PROVIDER_CAPABILITIES

        capability = PROVIDER_CAPABILITIES.get("elevenlabs")
        return bool(capability and language in capability.tts)
    return True


class CoverageGatedTTS:
    """A vendor voice that steps aside for languages the vendor cannot speak.

    The gate keeps the vendor wherever it has a voice and hands every other
    language to the synthetic TTS that was already there, which is correct in
    both shapes: a realtime mock falls back to its own tone, a cascade keeps the
    leg its router picked. What it must never do is let the vendor raise.
    """

    def __init__(self, vendor_tts, fallback_tts, vendor: str, settings: Settings):
        self.vendor_tts = vendor_tts
        self.fallback_tts = fallback_tts
        self.vendor = vendor
        self.settings = settings
        self.provider_name = getattr(vendor_tts, "provider_name", vendor)
        #: Languages the student asked for that this vendor had to decline.
        self.skipped: list[str] = []
        #: Session language/register, once the pipeline starts a session.
        self.language: str | None = None
        self.dialect: str | None = None

    def covers(self, language: str) -> bool:
        return vendor_covers_language(self.vendor, language, self.settings)

    async def synthesize_stream(self, text, language, *, voice=None):
        if not self.covers(language):
            if language not in self.skipped:
                self.skipped.append(language)
                logger.info(
                    "demo voice %s has no voice for '%s' - the synthetic voice speaks this one",
                    self.vendor,
                    language,
                )
            async for chunk in self.fallback_tts.synthesize_stream(text, language, voice=voice):
                yield chunk
            return
        async for chunk in self.vendor_tts.synthesize_stream(text, language, voice=voice):
            yield chunk

    def set_language_context(self, language: str, dialect: str | None = None) -> None:
        """Forward the session's language/register to whoever understands it.

        Only the vendor needs `dialect` (Arabic speaks with its fusHa voice); the
        synthetic fallback ignores it, which is why this is a soft protocol.
        """
        self.language = language
        self.dialect = dialect
        for tts in (self.vendor_tts, self.fallback_tts):
            hook = getattr(tts, "set_language_context", None)
            if hook is not None:
                hook(language, dialect)

    async def cancel(self) -> None:
        for tts in (self.vendor_tts, self.fallback_tts):
            cancel = getattr(tts, "cancel", None)
            if cancel is not None:
                await cancel()


def _build_elevenlabs(settings: Settings):
    from app.providers.elevenlabs.tts import ElevenLabsTTSProvider

    return ElevenLabsTTSProvider(settings)


def _build_azure(settings: Settings):
    from app.providers.azure.tts import AzureTTSProvider

    return AzureTTSProvider(settings)


#: vendor -> builder. Deliberately **not** the factory registry: with
#: VOICE_ENABLE_MOCK_PROVIDERS the registry rebinds vendor names to mocks, and a
#: mock "real voice" is exactly the bug this module exists to avoid. Tests swap
#: these out for a stub.
DEMO_TTS_BUILDERS: dict[str, object] = {"elevenlabs": _build_elevenlabs, "azure": _build_azure}


def attach_demo_voice(provider, factory, settings: Settings) -> str | None:
    """Give a *mock* pipeline a real TTS voice. Returns the vendor, or None.

    Only mock components are touched: a live `gemini-3.8-live` session already
    speaks with the model's own voice, and replacing the TTS of a real cascade
    would silently change the pipeline the router chose (and that /state reports).
    """
    vendor = demo_voice_vendor(settings)
    if vendor is None:
        return None

    from app.providers.mock.providers import MockRealtimeProvider, MockTTSProvider

    if isinstance(provider, MockRealtimeProvider):
        tts = CoverageGatedTTS(
            DEMO_TTS_BUILDERS[vendor](settings), MockTTSProvider(), vendor, settings
        )
        provider.attach_tts(tts, vendor)
        return vendor

    # A composed pipeline whose TTS leg is a mock (e.g. mock STT \u2192 mock LLM \u2192
    # mock TTS for a language the mocks cover). Swap only that leg.
    inner = getattr(provider, "tts", None)
    if isinstance(inner, MockTTSProvider):
        tts = CoverageGatedTTS(DEMO_TTS_BUILDERS[vendor](settings), inner, vendor, settings)
        old = provider.tts
        provider.tts = tts
        if hasattr(provider, "attach_tts"):  # keep the label honest
            provider.attach_tts(tts, vendor)
        else:
            provider.provider_name = provider.provider_name.replace(
                old.provider_name, f"{vendor}-voice"
            )
        logger.info(
            "demo voice: %s now speaks the composed pipeline %s",
            vendor,
            provider.provider_name,
        )
        return vendor
    return None
