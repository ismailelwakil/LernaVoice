"""Round 18: `POST /voice/session {"language": "ar-EG"}` must work, not 422.

The register lives in `dialect` today, but round-17 clients put it in `language`.
Both spellings now resolve to fusHa instead of failing the request.

Run once from the service root:  python3 tools/patch_arabic_accept_register.py
"""
import io


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


# --------------------------------------------------------------------------- #
# dialects.py: one place knows how a register can be spelled
# --------------------------------------------------------------------------- #

sub("app/voice/dialects.py", [
    (
        '''def dialect_for(language: str | None, dialect: str | None) -> Dialect | None:''',
        '''def split_language(value: str | None) -> tuple[str, str | None]:
    """Split an optional register off a language field: `ar-EG` -> (`ar`, `ar-MSA`).

    Clients wrote the register into `language` before there was a `dialect`
    field (`{"language": "ar-MSA"}`); both spellings must keep working, and both
    must land on the one register the service teaches. Non-Arabic codes come
    back unchanged, with no register.
    """
    raw = re.sub(r"\\s+", "", str(value or ""))
    base, _, tail = raw.partition("-")
    if base.lower() == "ar" and tail:
        return "ar", normalise_dialect("ar", raw)
    return raw.lower(), None


def dialect_for(language: str | None, dialect: str | None) -> Dialect | None:''',
    ),
])

# --------------------------------------------------------------------------- #
# schemas.py: accept, normalise, never fail an older client
# --------------------------------------------------------------------------- #

sub("app/api/schemas.py", [
    (
        "from pydantic import BaseModel, Field, field_validator",
        "from pydantic import BaseModel, Field, field_validator, model_validator",
    ),
    (
        "from app.voice.dialects import arabic_dialect_options, normalise_dialect",
        "from app.voice.dialects import arabic_dialect_options, normalise_dialect, split_language",
    ),
    (
        '''    @field_validator("language")
    @classmethod
    def _check_language(cls, v: str) -> str:
        v = (v or "en").lower()
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(SUPPORTED_LANGUAGES)}")
        return v

    @field_validator("dialect")
    @classmethod
    def _check_dialect(cls, v: str | None, info) -> str | None:
        return normalise_dialect(info.data.get("language"), v)''',
        '''    @model_validator(mode="after")
    def _check_language(self) -> "CreateSessionRequest":
        """`ar`, `ar-MSA` and the older `ar-EG` all start a fusHa Arabic lesson."""
        language, register = split_language(self.language)
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(SUPPORTED_LANGUAGES)}")
        self.language = language
        # A register written into `language` wins only when `dialect` is silent.
        self.dialect = normalise_dialect(language, self.dialect or register)
        return self''',
    ),
    (
        '''    @field_validator("language")
    @classmethod
    def _check(cls, v: str) -> str:
        raw = (v or "").strip()
        base = raw.split("-", 1)[0].lower()
        if base not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(SUPPORTED_LANGUAGES)}")
        return raw
        return v''',
        '''    @field_validator("language")
    @classmethod
    def _check(cls, v: str) -> str:
        body, _register = split_language(v)
        if body not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(SUPPORTED_LANGUAGES)}")
        return (v or "").strip()''',
    ),
])
print("schemas accept a register inside `language` and normalise it to ar-MSA")
