"""LERNA Voice AI Service — FastAPI application entrypoint."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse

from app import curriculum
from app.api.routes import health_router, router
from app.api.websocket import ws_router
from app.config import get_settings
from app.lerna_bridge import get_bridge
from app.logging_setup import configure_logging, get_logger, request_id_var
from app.learner.profiles import LearnerProfileStore
from app.persistence.repository import get_repository
from app.voice.events import ErrorCode
from app.voice.session_manager import get_manager

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = get_repository(settings)
    manager = get_manager()
    if settings.learner_profile_path and not getattr(manager.profiles, "path", None):
        # Remember each student's level across restarts; tests keep it in memory.
        manager.profiles = LearnerProfileStore(settings.learner_profile_path)
    bridge = get_bridge(settings)
    await bridge.ensure_ready()
    log.info(
        "voice service starting",
        extra={
            "env": settings.app_env,
            "providers": sorted(settings.configured_providers()),
            "persistence": repo.backend,
            "lerna": bridge.mode,
            "provider_mode": settings.voice_provider_mode,
        },
    )
    if settings.voice_auth_required and not settings.voice_service_api_key:
        log.warning(
            "VOICE_AUTH_REQUIRED is set but VOICE_SERVICE_API_KEY is empty — running OPEN. "
            "Set VOICE_SERVICE_API_KEY to enforce authentication.",
        )
    try:
        yield
    finally:
        await manager.shutdown()
        await bridge.aclose()
        await repo.aclose()
        log.info("voice service stopped")


app = FastAPI(
    title="LERNA Voice AI Service",
    description=(
        "Real-time multilingual voice tutoring for LERNA. Provider-agnostic: Gemini Live is "
        "primary, with ElevenLabs and Deepgram composed pipelines as backups."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

_cors = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=_cors != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:16]}"
    request_id_var.set(rid)
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "event": "error",
            "code": "VOICE_REQUEST_INVALID",
            "message": "The request payload is invalid.",
            "recoverable": False,
            "details": jsonable_encoder(exc.errors()[:5]) if not settings.is_production else None,
        },
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    # Never leak a stack trace in production (§47).
    log.error("unhandled error", extra={"error_type": type(exc).__name__, "path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={
            "event": "error",
            "code": ErrorCode.VOICE_INTERNAL_ERROR.value,
            "message": "Internal error.",
            "recoverable": True,
            "detail": None if settings.is_production else f"{type(exc).__name__}: {exc}",
        },
    )


app.include_router(health_router)
app.include_router(router)
app.include_router(ws_router)


STATIC_DIR = Path(__file__).parent / "static"
#: Keys the demo pages may read from the environment. Provider keys are never
#: injected — they stay server-side (see docs/DEPLOYMENT.md).
_PAGE_DEFAULTS = {
    "language": "en",
    "student_id": "demo-student-001",
    "course_id": "algorithms-101",
    "lesson_id": "lesson-binary-search",
    "topic": "Binary Search",
}
_LANGUAGES = OrderedDict(
    [
        ("en", "English"),
        ("ar", "العربية · Arabic"),
        ("fr", "Français"),
        ("sw", "Kiswahili"),
        ("am", "አማርኛ · Amharic"),
        ("ha", "Hausa"),
        ("so", "Soomaali"),
        ("yo", "Yorùbá"),
        ("ig", "Igbo"),
        ("zu", "isiZulu"),
    ]
)


def _inject(html: str, block_id: str, payload: dict) -> str:
    """Replace a page's JSON block with server-side data (no templating engine)."""
    return re.sub(
        rf'(<script id="{block_id}" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + json.dumps(payload, ensure_ascii=False) + m.group(2),
        html,
        count=1,
        flags=re.S,
    )


def _languages_payload() -> list[dict]:
    """Per-language routing facts for the demo pages (no credentials needed)."""
    from app.providers.capabilities import PROVIDER_CAPABILITIES
    from app.voice.provider_router import VoiceProviderRouter

    router = VoiceProviderRouter(available_providers=tuple(PROVIDER_CAPABILITIES))
    out = []
    for code, name in _LANGUAGES.items():
        plans = router.plan_pipelines(code, respect_health=False)
        out.append(
            {
                "code": code,
                "name": name,
                "realtime_native": any(p.pipeline.mode == "realtime" for p in plans),
                "primary_pipeline": plans[0].as_dict() if plans else None,
            }
        )
    return out


def _render_page(name: str) -> HTMLResponse | None:
    """Serve a self-contained demo page, injecting a safe config block.

    The pages ship with a `<script id="cfg" type="application/json">` block so
    they also work when opened as files; here we replace it with server-side
    defaults. `serviceUrl` is left empty, which makes the page talk to its own
    origin (same host as the WebSocket) — the robust choice behind port
    proxies, where cross-port calls get blocked.
    """
    path = STATIC_DIR / name
    if not path.exists():
        return None
    html = path.read_text(encoding="utf-8")
    if name == "topics.html":
        payload = {
            "courses": curriculum.list_courses(),
            "languages": _languages_payload(),
            "stats": curriculum.stats(),
            "defaultLanguage": "en",
            "greetings": curriculum.LOCALISED_GREETINGS,
        }
        return HTMLResponse(_inject(html, "catalog", payload))

    config = {
        "serviceUrl": "",
        "servicePort": os.getenv("VOICE_SERVICE_PUBLIC_PORT", "3000"),
        "apiKey": "",
        "resume_latest": False,
        "languages": dict(_LANGUAGES),
        "courses": curriculum.list_courses(),
        "languageRouting": _languages_payload(),
        **_PAGE_DEFAULTS,
    }
    return HTMLResponse(_inject(html, "cfg", config))


@app.get("/", include_in_schema=False)
async def root():
    """Voice-mode demo screen (self-contained HTML, no CDN assets).

    It is a testing surface for this service, not a product frontend; the
    production UI is owned by the LERNA web/mobile apps. Served from the same
    origin as the API and WebSocket so it works behind port proxies.
    """
    page = _render_page("voice_mode.html")
    if page is not None:
        return page
    return JSONResponse({"service": settings.service_name, "docs": "/docs", "health": "/health"})


@app.get("/voice", include_in_schema=False)
async def voice_page():
    """Alias of `/` — the topic picker links here with the chosen topic."""
    page = _render_page("voice_mode.html")
    if page is not None:
        return page
    return JSONResponse({"service": settings.service_name, "docs": "/docs", "health": "/health"})


@app.get("/topics", include_in_schema=False)
async def topics_page():
    """Topic picker: what the tutor can teach, and in which language."""
    page = _render_page("topics.html")
    if page is not None:
        return page
    return JSONResponse({"service": settings.service_name, "docs": "/docs", "health": "/health"})


@app.get("/console", include_in_schema=False)
async def console_page():
    """The lower-level developer console (raw events, controls, diagnostics)."""
    page = _render_page("console.html")
    if page is not None:
        return page
    return JSONResponse({"service": settings.service_name, "docs": "/docs", "health": "/health"})


@app.get("/info")
async def info() -> dict[str, str]:
    return {"service": settings.service_name, "docs": "/docs", "health": "/health"}
