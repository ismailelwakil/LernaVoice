"""Round 16: two Arabic registers (Egyptian + MSA) and a warmer Azure voice.

Backend patch. Run once from the service root:  python3 tools/patch_arabic_dialects.py
"""
import io
import os


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub(path, pairs):
    s = read(path)
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    write(path, s)


def sub_all(path, pairs):
    s = read(path)
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new)
    write(path, s)


# --------------------------------------------------------------------------- #
# A. the dialect registry
# --------------------------------------------------------------------------- #

DIALECTS = '''"""Arabic registers: Egyptian and Modern Standard, as real options.

Arabic is one of the ten mandatory languages, but it is taught in two registers
in practice, and a student in Cairo should not be answered in the same *voice* as
a student reading fusHa. The lesson is the same lesson: the language code stays
`ar` everywhere it matters (capability routing, provider plans, checkpoints,
Progress Profile signals, the canonical-English concept store). The dialect only
decides how the tutor *sounds*:

* which vendor voice reads the line (Egyptian `ar-EG-SalmaNeural` or MSA
  `ar-SA-ZariyahNeural`),
* which phrase set the offline dialogue speaks (`ar` vs `ar-msa`),
* which sentence the system instruction adds ("speak Egyptian Arabic" /
  "speak clear Modern Standard Arabic"), and
* the SSML `xml:lang` the vendor receives.

Anything else that asks "what language is this session?" keeps getting `ar`,
because that is what the rest of the system is built on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_ARABIC_DIALECT = "ar-EG"


@dataclass(frozen=True)
class Dialect:
    code: str
    english: str
    local: str
    lang_tag: str
    #: Vendor voice the demo speaks with (overridable with AZURE_VOICE_OVERRIDES).
    voice: str
    #: Language key the phrase tables answer to (see app/prompts/interaction.py).
    line_language: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "english": self.english,
            "local": self.local,
            "lang_tag": self.lang_tag,
            "voice": self.voice,
        }


ARABIC: tuple[Dialect, ...] = (
    Dialect("ar-EG", "Egyptian Arabic", "العربية المصرية", "ar-EG", "ar-EG-SalmaNeural", "ar"),
    Dialect("ar-MSA", "Modern Standard Arabic", "العربية الفصحى", "ar-SA", "ar-SA-ZariyahNeural", "ar-msa"),
)

DIALECTS: dict[str, Dialect] = {d.code: d for d in ARABIC}

#: What a student might type for each register (CLI, tests, the LERNA frontend).
_ALIASES = {
    "ar-eg": "ar-EG", "ar_eg": "ar-EG", "eg": "ar-EG", "egy": "ar-EG",
    "egyptian": "ar-EG", "masri": "ar-EG", "مصري": "ar-EG", "عامية": "ar-EG",
    "ar-msa": "ar-MSA", "ar_msa": "ar-MSA", "msa": "ar-MSA", "fusha": "ar-MSA",
    "fus7a": "ar-MSA", "standard": "ar-MSA", "ar-sa": "ar-MSA", "فصحى": "ar-MSA",
}


def normalise_dialect(language: str | None, dialect: str | None) -> str | None:
    """Canonical dialect code for a session, or None for non-Arabic languages."""
    if (language or "").lower() != "ar":
        return None
    if not dialect:
        return DEFAULT_ARABIC_DIALECT
    return _ALIASES.get(re.sub(r"\\s+", "", str(dialect).strip().lower()), DEFAULT_ARABIC_DIALECT)


def dialect_for(language: str | None, dialect: str | None) -> Dialect | None:
    code = normalise_dialect(language, dialect)
    return DIALECTS.get(code) if code else None


def dialect_voice(language: str | None, dialect: str | None) -> str | None:
    entry = dialect_for(language, dialect)
    return entry.voice if entry else None


def dialect_lang_tag(language: str | None, dialect: str | None) -> str | None:
    entry = dialect_for(language, dialect)
    return entry.lang_tag if entry else None


def line_language(language: str | None, dialect: str | None) -> str:
    """The phrase-table key: `ar-msa` for fusHa, the language itself otherwise."""
    entry = dialect_for(language, dialect)
    return entry.line_language if entry else (language or "en")


def arabic_dialect_options() -> list[dict[str, str]]:
    """Both registers, for GET /voice/languages."""
    return [d.as_dict() for d in ARABIC]
'''
write("app/voice/dialects.py", DIALECTS)

# --------------------------------------------------------------------------- #
# B. settings
# --------------------------------------------------------------------------- #

sub("app/config.py", [(
    """    azure_voice_overrides: str = \"\"""",
    """    azure_voice_overrides: str = ""
    #: Humanising the vendor voice: Azure's expressive style, a little pitch lift
    #: and short pauses between sentences. A tutor who breathes is a tutor you
    #: listen to; all three are ignored gracefully if a voice refuses the style.
    azure_tts_style: str = "cheerful"
    azure_tts_style_degree: float = 1.05
    azure_tts_pitch: float = 2.0
    azure_tts_pauses: bool = True""",
)])

# --------------------------------------------------------------------------- #
# C. Azure: dialect voice + humanised SSML
# --------------------------------------------------------------------------- #

sub("app/providers/azure/tts.py", [
    (
        '''Language coverage (verified against Microsoft's voice list): English, Arabic
(`ar-EG` Salma/Shakir), French, Swahili (`sw-KE`), Amharic (`am-ET`), Somali
(`so-SO`) and Zulu (`zu-ZA`) \\u2014 **not Hausa, not Yoruba, not Igbo**, the same
seven as the `edge-tts` voices, because it is the same voice catalogue.''',
        '''Language coverage (verified against Microsoft's voice list): English, Arabic
(French, Swahili (`sw-KE`), Amharic (`am-ET`), Somali
(`so-SO`) and Zulu (`zu-ZA`) \\u2014 **not Hausa, not Yoruba, not Igbo**, the same
seven as the `edge-tts` voices, because it is the same voice catalogue.

Arabic has two registers here and they are different voices, not different
settings: `ar-EG-SalmaNeural` (Egyptian) and `ar-SA-ZariyahNeural` (fusHa). The
SSML below is also what makes the voice sound like a person rather than an
announcement \\u2014 an expressive style, a slight pitch lift, short pauses between
sentences and moderate emphasis on the English technical terms.''',
    ),
    (
        '''from app.config import Settings, get_settings''',
        '''from app.config import Settings, get_settings
from app.voice.dialects import dialect_for, dialect_lang_tag, dialect_voice''',
    ),
    (
        '''#: One good voice per language (overridable with `AZURE_VOICE_<LANG>`).''',
        '''#: One good voice per language (overridable with `AZURE_VOICE_<LANG>` or,
#: for Arabic, `AZURE_VOICE_OVERRIDES=ar-EG:...,ar-MSA:...`).''',
    ),
    (
        '''def voice_for(language: str, settings: Settings | None = None) -> str | None:
    """The Azure voice for a language: configured override, else the default."""
    settings = settings or get_settings()
    overrides = getattr(settings, "azure_voice_overrides", "") or ""
    for pair in overrides.split(","):
        code, _, name = pair.partition(":")
        if code.strip().lower() == (language or "").lower() and name.strip():
            return name.strip()
    return DEFAULT_VOICES.get(language)''',
        '''def voice_for(
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
    wanted = {"ar-eg", "ar-msa", language} if language == "ar" else {language}
    wanted.discard("")
    for pair in overrides.split(","):
        code, _, name = pair.partition(":")
        if code.strip().lower() in wanted and name.strip():
            return name.strip()
    if entry is not None:
        return entry.voice
    return DEFAULT_VOICES.get(language)''',
    ),
    (
        '''    def _ssml(self, text: str, voice: str) -> str:
        rate = float(getattr(self.settings, "azure_speech_speed", 1.05))
        percent = int(round((rate - 1.0) * 100))
        prosody = f'<prosody rate="{percent:+d}%">' if percent else ""
        closing = "</prosody>" if percent else ""
        return (
            "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
            f"<voice name='{voice}'>{prosody}{escape(text)}{closing}</voice></speak>"
        )''',
        '''    def _ssml(self, text: str, voice: str, *, language: str = "en", dialect: str | None = None) -> str:
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
            out = _SENTENCE_END.sub(r'\\1 <break time="240ms"/>', out)
            out = _CLAUSE_END.sub(r'\\1 <break time="120ms"/>', out)
            out = out.replace(' <break time="120ms"/> <break time="240ms"/>',
                              ' <break time="240ms"/>')
        return out''',
    ),
    (
        '''    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._cancelled = False
        self.last_transport = "rest"''',
        '''    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._cancelled = False
        self.last_transport = "rest"
        #: Per-session register (`ar-EG` / `ar-MSA`), set by the pipeline at
        #: start_session; without it Arabic keeps the Egyptian default.
        self.language: str | None = None
        self.dialect: str | None = None
        #: Voices that rejected the expressive style: never ask them twice.
        self._style_refused: set[str] = set()

    def set_language_context(self, language: str, dialect: str | None = None) -> None:
        """Which language/register this session is taught in (see dialects.py)."""
        self.language = language
        self.dialect = dialect''',
    ),
])

sub_all("app/providers/azure/tts.py", [
    (
        '''from typing import AsyncIterator
from xml.sax.saxutils import escape''',
        '''import re
from typing import AsyncIterator
from xml.sax.saxutils import escape''',
    ),
    (
        '''AZURE_TTS_LANGUAGES = {"en", "ar", "fr", "sw", "am", "so", "zu"}''',
        '''AZURE_TTS_LANGUAGES = {"en", "ar", "fr", "sw", "am", "so", "zu"}

#: Sentence and clause boundaries a speaker would breathe at.
_SENTENCE_END = re.compile(r"([.!?\\u061f\\u06d4])\\s+")
_CLAUSE_END = re.compile(r"([\\u060c,])\\s+")
#: English technical terms kept in English (\\u00a714) - they deserve the stress.
_LATIN_RUN = re.compile(r"\\b[A-Za-z][A-Za-z0-9+#./-]{2,}(?:\\s+[A-Za-z][A-Za-z0-9+#./-]{2,})*\\b")''',
    ),
])
print("A-C ok")

# the provider call site: pass the register through and retry once without style
sub_all("app/providers/azure/tts.py", [
    (
        '''        selected = voice or voice_for(language, self.settings)''',
        '''        selected = voice or voice_for(language, self.settings, self.dialect)''',
    ),
    (
        '''                    content=self._ssml(text, selected).encode("utf-8"),''',
        '''                    content=self._ssml(
                        text, selected, language=language, dialect=self.dialect
                    ).encode("utf-8"),''',
    ),
])

# a style the voice does not support is not an error: retry without it once
sub("app/providers/azure/tts.py", [(
    '''        if response.status_code >= 400:
            detail = response.text[:200]''',
    '''        if response.status_code == 400 and self._ssml_has_style(text, selected, language):
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
            detail = response.text[:200]''',
)])

sub("app/providers/azure/tts.py", [(
    '''    async def cancel(self) -> None:
        self._cancelled = True''',
    '''    async def cancel(self) -> None:
        self._cancelled = True

    def _ssml_has_style(self, text: str, voice: str, language: str) -> bool:
        style = (getattr(self.settings, "azure_tts_style", "") or "").strip()
        return bool(style) and voice not in self._style_refused''',
)])
print("azure ok")
