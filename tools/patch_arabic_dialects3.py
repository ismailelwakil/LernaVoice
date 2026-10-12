"""Round 16, part 3: the dialogue speaks the register, the voice gets it too.

Run once from the service root:  python3 tools/patch_arabic_dialects3.py
"""
import io


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub(path, pairs, all_=False):
    s = read(path)
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new) if all_ else s.replace(old, new, 1)
    write(path, s)


# --------------------------------------------------------------------------- #
# the dialogue speaks the session's register
# --------------------------------------------------------------------------- #

sub("app/providers/mock/dialogue.py", [
    (
        '''from app.prompts.interaction import (''',
        '''from app.voice.dialects import line_language
from app.prompts.interaction import (''',
    ),
    (
        '''    language: str = "en"
    sections: list[dict[str, str]] = field(default_factory=list)''',
        '''    language: str = "en"
    #: Which phrase table answers: Arabic in fusHa has its own (`ar-msa`), while
    #: `language` stays `ar` for localisation, separators and canonical concepts.
    line_language: str = "en"
    sections: list[dict[str, str]] = field(default_factory=list)''',
    ),
    (
        '''        return cls(
            language=language,
            sections=sections,''',
        '''        return cls(
            language=language,
            line_language=line_language(language, md.get("dialect")),
            sections=sections,''',
    ),
    (
        '''    def _p(self, key: str) -> str:
        return phrase(self.language, key)''',
        '''    def _p(self, key: str) -> str:
        return phrase(self.line_language, key)''',
    ),
    (
        '''        options = phrase_variants(self.language, key)''',
        '''        options = phrase_variants(self.line_language, key)''',
    ),
    (
        '''        return step_lead(
            self.language,''',
        '''        return step_lead(
            self.line_language,''',
    ),
    (
        '''        template = phrase(self.language, key)
        try:
            return template.format(**parts)''',
        '''        template = phrase(self.line_language, key)
        try:
            return template.format(**parts)''',
    ),
    (
        '''        greeting = LOCALISED_GREETINGS.get(self.language, LOCALISED_GREETINGS["en"])''',
        '''        greeting = (
            LOCALISED_GREETINGS.get(self.line_language)
            or LOCALISED_GREETINGS.get(self.language)
            or LOCALISED_GREETINGS["en"]
        )''',
    ),
    (
        '''            f"{move_on(self.language, 0)} {self._lead(first)} "''',
        '''            f"{move_on(self.line_language, 0)} {self._lead(first)} "''',
    ),
    (
        '''        return self._name(f"{react(self.language, self._variety)} {self._p('holding')}")''',
        '''        return self._name(f"{react(self.line_language, self._variety)} {self._p('holding')}")''',
    ),
    (
        '''        return f"{react(self.language, self._variety)} {self._p('going_on')}"''',
        '''        return f"{react(self.line_language, self._variety)} {self._p('going_on')}"''',
    ),
], all_=True)

# --------------------------------------------------------------------------- #
# the pipeline tells the vendor voice which language/register the session is in
# --------------------------------------------------------------------------- #

sub("app/providers/mock/providers.py", [
    (
        '''        self.tts = None
        self.tts_vendor: str | None = None''',
        '''        self.tts = None
        self.tts_vendor: str | None = None
        #: Arabic register of this session (`ar-EG` / `ar-MSA`), if any.
        self.dialect: str | None = None''',
    ),
    (
        '''        self.tts_voice = (config.metadata or {}).get("tts_voice_id") or None
        self.language = config.language
        self._open = True''',
        '''        self.tts_voice = (config.metadata or {}).get("tts_voice_id") or None
        self.language = config.language
        self.dialect = (config.metadata or {}).get("dialect") or None
        # A vendor voice that has more than one voice for a language (Arabic in
        # fusHa vs Egyptian) needs to know which one this session speaks in.
        _context = getattr(self.tts, "set_language_context", None)
        if _context is not None:
            _context(config.language, self.dialect)
        self._open = True''',
    ),
])

sub("app/providers/cascade.py", [
    (
        '''    async def start_session(self, config: SessionConfig) -> None:
        self._config = config
        self._messages = [dict(m) for m in config.initial_context]''',
        '''    async def start_session(self, config: SessionConfig) -> None:
        self._config = config
        self._messages = [dict(m) for m in config.initial_context]
        _context = getattr(self.tts, "set_language_context", None)
        if _context is not None:
            _context(config.language, (config.metadata or {}).get("dialect"))''',
    ),
])

sub("app/voice/demo_voice.py", [
    (
        '''    async def cancel(self) -> None:
        for tts in (self.vendor_tts, self.fallback_tts):
            cancel = getattr(tts, "cancel", None)
            if cancel is not None:
                await cancel()''',
        '''    def set_language_context(self, language: str, dialect: str | None = None) -> None:
        """Forward the session's language/register to whoever understands it.

        Only the vendor needs `dialect` (Arabic: Egyptian vs fusHa voice); the
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
                await cancel()''',
    ),
    (
        '''        self.provider_name = getattr(vendor_tts, "provider_name", vendor)
        #: Languages the student asked for that this vendor had to decline.
        self.skipped: list[str] = []''',
        '''        self.provider_name = getattr(vendor_tts, "provider_name", vendor)
        #: Languages the student asked for that this vendor had to decline.
        self.skipped: list[str] = []
        #: Session language/register, once the pipeline starts a session.
        self.language: str | None = None
        self.dialect: str | None = None''',
    ),
])
print("dialogue + pipeline context ok")
