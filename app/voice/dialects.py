"""Arabic is taught in Modern Standard Arabic (fusHa).

Arabic is one of the ten mandatory languages; this service teaches it in
`ar-MSA`. The language code stays `ar` everywhere it matters - capability
routing, pipeline plans, checkpoints, Progress Profile signals, the
canonical-English concept store - and the register only decides how the tutor
sounds: the vendor voice (`ar-SA-ZariyahNeural`), the sentence the system
instruction adds ("speak clear Modern Standard Arabic"), and the SSML
`xml:lang` the vendor receives.

The register is still a *session property* (`dialect`) rather than a constant,
because clients sent `ar-EG` before this change: `normalise_dialect` maps every
Egyptian spelling onto `ar-MSA` instead of failing, so an older client gets
formal Arabic rather than a broken lesson. Re-adding a second register later is
one entry in `ARABIC` plus its phrase table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_ARABIC_DIALECT = "ar-MSA"


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
    Dialect("ar-MSA", "Modern Standard Arabic", "\u0627\u0644\u0639\u0631\u0628\u064a\u0629 \u0627\u0644\u0641\u0635\u062d\u0649", "ar-SA", "ar-SA-ZariyahNeural", "ar"),
    # Round 24: a second, optional register — polite Egyptian Arabic. fusHa stays the
    # default; a student (or client) can pick `ar-EG` and get a respectful Egyptian
    # voice (`ar-EG-SalmaNeural`) with Egyptian interaction lines (app/prompts).
    Dialect("ar-EG", "Egyptian Arabic (polite)", "\u0639\u0627\u0645\u064a\u0629 \u0645\u0635\u0631\u064a\u0629 \u0645\u0647\u0630\u0628\u0629", "ar-EG", "ar-EG-SalmaNeural", "ar-eg"),
)

DIALECTS: dict[str, Dialect] = {d.code: d for d in ARABIC}

#: What a client might send. fusHa spellings stay fusHa; Egyptian spellings now map to
#: the polite Egyptian register (round 24) instead of being folded into fusHa.
_ALIASES = {
    "ar-msa": "ar-MSA", "ar_msa": "ar-MSA", "msa": "ar-MSA", "fusha": "ar-MSA",
    "fus7a": "ar-MSA", "standard": "ar-MSA", "ar-sa": "ar-MSA", "\u0641\u0635\u062d\u0649": "ar-MSA",
    "ar-eg": "ar-EG", "ar_eg": "ar-EG", "eg": "ar-EG", "egy": "ar-EG",
    "egyptian": "ar-EG", "masri": "ar-EG", "\u0645\u0635\u0631\u064a": "ar-EG", "\u0639\u0627\u0645\u064a\u0629": "ar-EG",
}


def normalise_dialect(language: str | None, dialect: str | None) -> str | None:
    """Canonical register for a session (Arabic only): always `ar-MSA` today."""
    if (language or "").lower() != "ar":
        return None
    if not dialect:
        return DEFAULT_ARABIC_DIALECT
    return _ALIASES.get(re.sub(r"\s+", "", str(dialect).strip().lower()), DEFAULT_ARABIC_DIALECT)


def split_language(value: str | None) -> tuple[str, str | None]:
    """Split an optional register off a language field: `ar-EG` -> (`ar`, `ar-MSA`).

    Clients wrote the register into `language` before there was a `dialect`
    field (`{"language": "ar-MSA"}`); both spellings must keep working, and both
    must land on the one register the service teaches. Non-Arabic codes come
    back unchanged, with no register.
    """
    raw = re.sub(r"\s+", "", str(value or ""))
    parts = re.split(r"[-_]", raw, maxsplit=1)
    base = parts[0]
    tail = parts[1] if len(parts) > 1 else None
    if base.lower() == "ar" and tail:
        return "ar", normalise_dialect("ar", raw)
    return raw.lower(), None


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
    """The phrase-table key: Arabic's own table is the formal one."""
    entry = dialect_for(language, dialect)
    return entry.line_language if entry else (language or "en")


def arabic_dialect_options() -> list[dict[str, str]]:
    """The registers on offer, for GET /voice/languages."""
    return [d.as_dict() for d in ARABIC]
