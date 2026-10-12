"""Patch: humanised Gemini Live settings, /health visibility, page prefers the real voice."""

# ============================================================ config.py
P = "app/config.py"
s = open(P).read()

s = s.replace(
    '    gemini_voice_name: str = "Kore"',
    '''    gemini_voice_name: str = "Kore"
    #: Affective dialog lets the native-audio model adapt its tone to how the student
    #: sounds (frustrated, unsure, pleased) instead of delivering flat narration.
    gemini_affective_dialog: bool = True
    #: Proactive audio lets the model speak up when it has something useful to add.
    #: Off by default: a tutor should answer the student, not fill every silence.
    gemini_proactive_audio: bool = False''',
)

anchor = "    def active_gemini_live_model(self) -> str:"
assert anchor in s
s = s.replace(
    anchor,
    '''    @property
    def gemini_auth_mode(self) -> str:
        """Which Gemini auth path is wired: vertex, developer_api, or none.

        Reported by `/health` (a name, never a credential) so the demo knows whether a
        real vendor voice is available or it is running on the mock.
        """
        if not self.gemini_api_key and not self.google_application_credentials:
            return "none"
        return "vertex" if self.google_genai_use_vertexai else "developer_api"

''' + anchor,
    1,
)
open(P, "w").write(s)

# ============================================================ gemini/live.py
P = "app/providers/gemini/live.py"
s = open(P).read()

old = '''            if config.tools:
                live_config["tools"] = [{"function_declarations": config.tools}]

            self._cm = self._client.aio.live.connect(model=self._model, config=live_config)
            self._session = await asyncio.wait_for(
                self._cm.__aenter__(), timeout=self.settings.voice_provider_timeout
            )'''
new = '''            if config.tools:
                live_config["tools"] = [{"function_declarations": config.tools}]

            # Humanising options on top of the base setup. They are attempted first and
            # dropped if the model/auth path rejects them, so an older live model still
            # connects instead of failing the whole session over a nicety.
            extras: dict[str, Any] = {}
            if self.settings.gemini_affective_dialog:
                extras["enable_affective_dialog"] = True
            if self.settings.gemini_proactive_audio:
                extras["proactivity"] = {"proactive_audio": True}

            attempts = ([{**live_config, **extras}, live_config] if extras else [live_config])
            last: Exception | None = None
            for candidate in attempts:
                try:
                    self._cm = self._client.aio.live.connect(model=self._model, config=candidate)
                    self._session = await asyncio.wait_for(
                        self._cm.__aenter__(), timeout=self.settings.voice_provider_timeout
                    )
                    if "enable_affective_dialog" in candidate:
                        log.info("gemini live: affective dialog on", extra={"model": self._model})
                    break
                except Exception as exc:  # noqa: BLE001 — re-raised below when unretryable
                    last = exc
                    self._cm = None
                    self._session = None
                    if candidate is attempts[-1] or not _looks_like_setup_rejection(exc):
                        raise classify_gemini_error(exc) from exc
                    log.warning(
                        "gemini live rejected the humanising options, retrying without them",
                        extra={"error": str(exc)[:200]},
                    )
            if self._session is None and last is not None:      # pragma: no cover - defensive
                raise classify_gemini_error(last)'''
assert old in s
s = s.replace(old, new)

s = s.replace(
    "from app.logging_setup import get_logger",
    '''from app.logging_setup import get_logger

#: Setup fields a model may reject. Only *these* failures are retried without the
#: optional humanising options — a network error must fail over immediately.
_SETUP_REJECTION_HINTS = ("invalid", "unknown field", "unexpected", "validation", "unsupported")''',
)

s = s.rstrip() + '''


def _looks_like_setup_rejection(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(hint in text for hint in _SETUP_REJECTION_HINTS)
'''
open(P, "w").write(s)

# ============================================================ /health visibility
P = "app/api/schemas.py"
s = open(P).read()
s = s.replace(
    '''class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    service: str = "lerna-voice-ai"
    version: str = "1.0.0"''',
    '''class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    service: str = "lerna-voice-ai"
    version: str = "1.0.0"
    # Operational shape, never credentials: which pipeline is in use and whether the
    # audio is coming from a real vendor or the offline mock. The demo screen uses
    # `mock_providers` to decide whether to voice the transcript itself.
    provider_mode: str = "auto"
    mock_providers: bool = False
    live_model: str | None = None
    gemini_auth: str = "none"''',
)
open(P, "w").write(s)

P = "app/api/routes.py"
s = open(P).read()
s = s.replace(
    '''async def health() -> HealthResponse:
    return HealthResponse(status="ok", service=get_settings().service_name)''',
    '''async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        provider_mode=settings.voice_provider_mode,
        mock_providers=settings.voice_enable_mock_providers,
        live_model=settings.active_gemini_live_model,
        gemini_auth=settings.gemini_auth_mode,
    )''',
)
open(P, "w").write(s)

import subprocess
print(subprocess.run(["python3", "-c", "import app.main; from app.config import Settings; print('auth mode:', Settings().gemini_auth_mode)"],
                     capture_output=True, text=True).stdout)
