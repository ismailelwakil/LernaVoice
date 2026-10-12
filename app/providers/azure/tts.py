"""Azure AI Speech TTS \u2014 the official free-tier voice (F0: 0.5M characters/month).

One HTTP call per line, `riff-<rate>khz-16bit-mono-pcm` output; the 44-byte WAV
header is dropped so what the client receives is exactly the same PCM16 the
Gemini Live and ElevenLabs paths emit.

Language coverage (verified against Microsoft's voice list): English, Arabic
(French, Swahili (`sw-KE`), Amharic (`am-ET`), Somali
(`so-SO`) and Zulu (`zu-ZA`) \u2014 **not Hausa, not Yoruba, not Igbo**, the same
seven as the `edge-tts` voices, because it is the same voice catalogue.

Arabic is spoken in fusHa (`ar-SA-ZariyahNeural`); an Egyptian voice
(`ar-EG-SalmaNeural`) is still one `AZURE_VOICE_OVERRIDES` entry away. The
SSML below is also what makes the voice sound like a person rather than an
announcement \u2014 an expressive style, a slight pitch lift, short pauses between
sentences and moderate emphasis on the English technical terms.
"""

from __future__ import annotations

import re
from typing import AsyncIterator
from xml.sax.saxutils import escape

from app.config import Settings, get_settings
from app.voice.dialects import dialect_for, dialect_lang_tag, dialect_voice
from app.providers.base import (
    AudioChunk,
    ProviderAuthError,
    ProviderUnsupportedError,
    TextToSpeechProvider,
)
from app.providers.capabilities import PROVIDER_CAPABILITIES, Capability
from app.providers.ws_utils import classify_exception

AZURE_TTS_LANGUAGES = {"en", "ar", "fr", "sw", "am", "so", "zu"}

#: Sentence and clause boundaries a speaker would breathe at.
_SENTENCE_END = re.compile(r"([.!?\u061f\u06d4])\s+")
_CLAUSE_END = re.compile(r"([\u060c,])\s+")
#: English technical terms kept in English (\u00a714) - they deserve the stress.
_LATIN_RUN = re.compile(r"\b[A-Za-z][A-Za-z0-9+#./-]{2,}(?:\s+[A-Za-z][A-Za-z0-9+#./-]{2,})*\b")

#: One good voice per language (overridable with `AZURE_VOICE_<LANG>` or,
#: for Arabic, `AZURE_VOICE_OVERRIDES=ar-EG:...,ar-MSA:...`).
DEFAULT_VOICES: dict[str, str] = {
    "en": "en-US-AvaMultilingualNeural",
    #: Arabic is taught in fusHa: `ar-SA-ZariyahNeural` (see app/voice/dialects.py).
    "ar": "ar-SA-ZariyahNeural",
    "fr": "fr-FR-DeniseNeural",
    "sw": "sw-KE-ZuriNeural",
    "am": "am-ET-MekdesNeural",
    "so": "so-SO-UbaxNeural",
    "zu": "zu-ZA-ThandoNeural",
}


def voice_for(
    language: str, settings: Settings | None = None, dialect: str | None = None
) -> str | None:
    """The Azure voice for a language (and Arabic register): override, else default.

    `dialect` accepts `ar-EG` / `ar-MSA` (or an alias such as `msa`, `fusha`,
    `egyptian`); anything else is ignored, so a caller that only knows the
    language still gets the Egyptian default for Arabic.
    """
    settings = settings or get_settings()
    language = (language or "").lower()
    entry = dialect_for(language, dialect) if language == "ar" else None
    overrides = getattr(settings, "azure_voice_overrides", "") or ""
    # Most specific first: the register (`ar-MSA`), then the plain language (`ar`).
    wanted = [entry.code.lower() if entry else None, language] if language == "ar" else [language]
    for key in [w for w in wanted if w]:
        for pair in overrides.split(","):
            code, _, name = pair.partition(":")
            if code.strip().lower() == key and name.strip():
                return name.strip()
    if entry is not None:
        return entry.voice
    return DEFAULT_VOICES.get(language)


class AzureTTSProvider(TextToSpeechProvider):
    provider_name = "azure"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._cancelled = False
        self.last_transport = "rest"
        #: Per-session register, set by the pipeline at start_session; Arabic
        #: is taught in fusHa, so without it the formal voice is used.
        self.language: str | None = None
        self.dialect: str | None = None
        #: Voices that rejected the expressive style: never ask them twice.
        self._style_refused: set[str] = set()

    def set_language_context(self, language: str, dialect: str | None = None) -> None:
        """Which language/register this session is taught in (see dialects.py)."""
        self.language = language
        self.dialect = dialect

    async def cancel(self) -> None:
        self._cancelled = True

    def _ssml_has_style(self, text: str, voice: str, language: str) -> bool:
        style = (getattr(self.settings, "azure_tts_style", "") or "").strip()
        return bool(style) and voice not in self._style_refused

    def _ssml(self, text: str, voice: str, *, language: str = "en", dialect: str | None = None) -> str:
        """Human speech, not an announcement.

        Four deliberate choices, all visible in the audio: the vendor's expressive
        style (cheerful by default) with a small degree, a slight pitch lift, short
        `<break>`s where a speaker would breathe, and moderate emphasis on the
        English technical terms so "binary search" lands inside an Arabic sentence.
        """
        rate = float(getattr(self.settings, "azure_speech_speed", 1.05))
        pitch = float(getattr(self.settings, "azure_tts_pitch", 2.0))
        percent = int(round((rate - 1.0) * 100))
        attributes = []
        if percent:
            attributes.append(f'rate="{percent:+d}%"')
        if pitch:
            attributes.append(f'pitch="{pitch:+.0f}%"')
        prosody = f"<prosody {' '.join(attributes)}>" if attributes else ""
        closing = "</prosody>" if prosody else ""

        body = self._humanise(text)
        style = (getattr(self.settings, "azure_tts_style", "") or "").strip()
        if style and voice not in self._style_refused:
            degree = float(getattr(self.settings, "azure_tts_style_degree", 1.05))
            body = (
                f'<mstts:express-as style="{style}" styledegree="{degree:g}">'
                f"{prosody}{body}{closing}</mstts:express-as>"
            )
        else:
            body = f"{prosody}{body}{closing}"

        lang_tag = dialect_lang_tag(language, dialect) or "en-US"
        if lang_tag == "ar-SA":
            lang_tag = "ar-SA"
        elif len(lang_tag) == 2:
            lang_tag = {"en": "en-US", "ar": "ar-EG", "fr": "fr-FR", "sw": "sw-KE",
                        "am": "am-ET", "so": "so-SO", "zu": "zu-ZA"}.get(lang_tag, lang_tag)
        return (
            "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
            "xmlns:mstts='https://www.w3.org/2001/mstts' "
            f"xml:lang='{lang_tag}'>"
            f"<voice name='{voice}'>{body}</voice></speak>"
        )

    def _humanise(self, text: str) -> str:
        """Turns between sentences, a beat at commas, emphasis on Latin terms."""
        pauses = bool(getattr(self.settings, "azure_tts_pauses", True))
        pieces: list[str] = []
        cursor = 0
        for match in _LATIN_RUN.finditer(text):
            pieces.append(escape(text[cursor:match.start()]))
            pieces.append(f'<emphasis level="moderate">{escape(match.group(0))}</emphasis>')
            cursor = match.end()
        pieces.append(escape(text[cursor:]))
        out = "".join(pieces)
        if pauses:
            out = _SENTENCE_END.sub(r'\1 <break time="240ms"/>', out)
            out = _CLAUSE_END.sub(r'\1 <break time="120ms"/>', out)
            out = out.replace(' <break time="120ms"/> <break time="240ms"/>',
                              ' <break time="240ms"/>')
        return out

    async def synthesize_stream(
        self, text: str, language: str, *, voice: str | None = None
    ) -> AsyncIterator[AudioChunk]:
        capability = PROVIDER_CAPABILITIES.get("azure")
        if capability is None or not capability.supports(Capability.TTS, language):
            raise ProviderUnsupportedError(
                f"Azure TTS does not cover '{language}'", provider="azure"
            )
        key = getattr(self.settings, "azure_speech_key", None)
        region = getattr(self.settings, "azure_speech_region", None)
        if not key or not region:
            raise ProviderAuthError(
                "AZURE_SPEECH_KEY / AZURE_SPEECH_REGION are not configured", provider="azure"
            )

        selected = voice or voice_for(language, self.settings, self.dialect)
        if not selected:
            raise ProviderUnsupportedError(f"no Azure voice for '{language}'", provider="azure")

        rate_khz = max(8, min(48, int(self.settings.output_sample_rate) // 1000))
        import httpx

        try:
            async with httpx.AsyncClient(timeout=self.settings.voice_provider_timeout * 3) as client:
                response = await client.post(
                    f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                    headers={
                        "Ocp-Apim-Subscription-Key": key,
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": f"riff-{rate_khz}khz-16bit-mono-pcm",
                        "User-Agent": "lerna-voice-ai",
                    },
                    content=self._ssml(
                        text, selected, language=language, dialect=self.dialect
                    ).encode("utf-8"),
                )
        except Exception as exc:  # noqa: BLE001
            raise classify_exception(exc, "azure") from exc

        if response.status_code == 400 and self._ssml_has_style(text, selected, language):
            # `mstts:express-as` is per-voice; a voice that refuses the style must
            # still speak the line. Remember it and retry once without the style.
            self._style_refused.add(selected)
            import httpx

            async with httpx.AsyncClient(timeout=self.settings.voice_provider_timeout * 3) as client:
                response = await client.post(
                    f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                    headers={
                        "Ocp-Apim-Subscription-Key": key,
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": f"riff-{rate_khz}khz-16bit-mono-pcm",
                        "User-Agent": "lerna-voice-ai",
                    },
                    content=self._ssml(
                        text, selected, language=language, dialect=self.dialect
                    ).encode("utf-8"),
                )

        if response.status_code >= 400:
            detail = response.text[:200]
            if response.status_code in (401, 403):
                raise ProviderAuthError(
                    f"Azure refused the key ({response.status_code}): {detail}", provider="azure"
                )
            raise classify_exception(
                RuntimeError(f"HTTP {response.status_code}: {detail}"), "azure"
            )

        pcm = _strip_wav(response.content)
        if self._cancelled or not pcm:
            return
        step = self.settings.output_sample_rate // 5 * 2  # ~200 ms, like the other paths
        for offset in range(0, len(pcm), step):
            if self._cancelled:
                return
            yield AudioChunk(data=pcm[offset : offset + step], sample_rate=self.settings.output_sample_rate)


def _strip_wav(data: bytes) -> bytes:
    """Drop the RIFF header (Azure returns a WAV container); keep the PCM."""
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        index = data.find(b"data")
        if index != -1:
            return data[index + 8 :]
    return data
