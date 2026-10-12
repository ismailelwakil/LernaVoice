"""REST API (§35, §60)."""

from __future__ import annotations

from typing import Any

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.api.schemas import (
    CreateSessionRequest,
    HealthResponse,
    InterruptResponse,
    LanguageChangeRequest,
    LevelChangeRequest,
    QuestionRequest,
    QuestionResponse,
    ResumeResponse,
    SessionStateResponse,
    SessionSummary,
    SimpleResponse,
)
from app.api.security import Principal, require_service_auth, token_store
from app.config import get_settings
from app import curriculum
from app.lerna_bridge import get_bridge
from app.providers.capabilities import PROVIDER_CAPABILITIES, capability_matrix
from app.voice.demo_voice import demo_voice_label, demo_voice_vendor
from app.voice.events import ErrorCode
from app.voice.interruption_manager import InterruptionManager
from app.voice.provider_router import UnsupportedLanguageError
from app.voice.resume_manager import ResumeManager
from app.voice.session_manager import VoiceSession, get_manager
from app.voice.dialects import arabic_dialect_options
from app.voice.state import LANGUAGE_NAMES, SUPPORTED_LANGUAGES

router = APIRouter()
health_router = APIRouter()


def _error(code: ErrorCode, message: str, http_status: int, recoverable: bool = True) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"event": "error", "code": code.value, "message": message, "recoverable": recoverable},
    )


async def _session_or_404(session_id: str) -> VoiceSession:
    manager = get_manager()
    session = await manager.get(session_id)
    if session is None:
        raise _error(
            ErrorCode.VOICE_SESSION_NOT_FOUND,
            f"Unknown voice session '{session_id}'.",
            status.HTTP_404_NOT_FOUND,
            recoverable=False,
        )
    return session


def _summary(session: VoiceSession, request: Request | None = None) -> SessionSummary:
    state = session.state
    ws_url = None
    if request is not None:
        scheme = "wss" if request.url.scheme == "https" else "ws"
        ws_url = f"{scheme}://{request.url.netloc}/voice/session/{state.session_id}/audio"
    return SessionSummary(
        session_id=state.session_id,
        student_id=state.student_id,
        course_id=state.course_id,
        lesson_id=state.lesson_id,
        language=state.language,
        dialect=state.dialect,
        student_level=state.student_level,
        state=state.state.value,
        current_topic=state.current_topic,
        current_section=state.current_section,
        interrupt_count=state.interrupt_count,
        resume_count=state.resume_count,
        active_pipeline=state.active_pipeline.model_dump(),
        created_at=state.created_at,
        updated_at=state.updated_at,
        websocket_url=ws_url,
    )


# --------------------------------------------------------------------------- #
# sessions
# --------------------------------------------------------------------------- #


@router.post("/voice/session", response_model=SessionSummary, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: CreateSessionRequest,
    request: Request,
    principal: Principal = Depends(require_service_auth),
) -> SessionSummary:
    manager = get_manager()
    session = await manager.create(
        student_id=payload.student_id,
        language=payload.language,
        course_id=payload.course_id,
        lesson_id=payload.lesson_id,
        topic=payload.topic,
        topic_id=payload.topic_id,
        document_ids=payload.document_ids,
        dialect=payload.dialect,
        level=payload.level,
        resume_latest=payload.resume_latest,
    )
    return _summary(session, request)


@router.get("/voice/session/{session_id}", response_model=SessionSummary)
async def get_session(
    session_id: str, request: Request, principal: Principal = Depends(require_service_auth)
) -> SessionSummary:
    return _summary(await _session_or_404(session_id), request)


@router.get("/voice/session/{session_id}/state", response_model=SessionStateResponse)
async def get_session_state(
    session_id: str, principal: Principal = Depends(require_service_auth)
) -> SessionStateResponse:
    session = await _session_or_404(session_id)
    state = session.state
    settings = get_settings()
    return SessionStateResponse(
        session_id=state.session_id,
        state=state.state.value,
        language=state.language,
        dialect=state.dialect,
        student_level=state.student_level,
        current_topic=state.current_topic,
        current_section=state.current_section,
        topic_id=state.topic_id,
        lesson_plan=list(state.lesson_plan),
        concepts_covered=state.concepts_covered,
        student_questions=[q.model_dump() for q in state.student_questions],
        interrupt_count=state.interrupt_count,
        resume_count=state.resume_count,
        is_returning=state.is_returning,
        previous_session_id=state.previous_session_id,
        checkpoint=state.resume_checkpoint.model_dump() if state.resume_checkpoint else None,
        unresolved_questions=state.unresolved_questions,
        misconceptions=state.misconceptions,
        session_summary=state.session_summary,
        next_action=state.next_action,
        active_pipeline=state.active_pipeline.model_dump(),
        explanation=state.explanation,
        provider_history=[t.model_dump() for t in state.provider_history],
        diagnostics=session.diagnostics() if settings.expose_dev_diagnostics else None,
    )


@router.get("/voice/session/{session_id}/history")
async def get_session_history(
    session_id: str, principal: Principal = Depends(require_service_auth)
) -> dict[str, Any]:
    session = await _session_or_404(session_id)
    return await session.repository.history(session_id)


@router.post("/voice/session/{session_id}/token")
async def issue_client_token(
    session_id: str, principal: Principal = Depends(require_service_auth)
) -> dict[str, Any]:
    """Short-lived token so a browser can open the WS without the service key."""
    await _session_or_404(session_id)
    return token_store.issue(session_id)


@router.post("/voice/session/{session_id}/start", response_model=SessionSummary)
async def start_session(
    session_id: str,
    request: Request,
    recap: bool | None = None,
    principal: Principal = Depends(require_service_auth),
) -> SessionSummary:
    session = await _session_or_404(session_id)
    try:
        await session.start(recap=recap)
    except UnsupportedLanguageError as exc:
        raise _error(
            ErrorCode.VOICE_LANGUAGE_UNSUPPORTED, str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY, False
        ) from exc
    except Exception as exc:
        raise _error(
            ErrorCode.VOICE_PROVIDER_UNAVAILABLE,
            "Voice service is temporarily unavailable.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    return _summary(session, request)


@router.post("/voice/session/{session_id}/interrupt", response_model=InterruptResponse)
async def interrupt_session(
    session_id: str, principal: Principal = Depends(require_service_auth)
) -> InterruptResponse:
    session = await _session_or_404(session_id)
    try:
        result = await InterruptionManager(session).interrupt()
    except RuntimeError as exc:
        raise _error(ErrorCode.VOICE_SESSION_INVALID_STATE, str(exc), status.HTTP_409_CONFLICT) from exc
    return InterruptResponse(
        session_id=session_id,
        state=session.state.state.value,
        checkpoint=result["checkpoint"],
        acknowledgement=result["acknowledgement"],
        playback_stop_ms=result.get("stop_ms"),
    )


@router.post("/voice/session/{session_id}/question", response_model=QuestionResponse)
async def ask_question(
    session_id: str, payload: QuestionRequest, principal: Principal = Depends(require_service_auth)
) -> QuestionResponse:
    session = await _session_or_404(session_id)
    result = await InterruptionManager(session).ask(payload.text)
    return QuestionResponse(session_id=session_id, **result)


@router.post("/voice/session/{session_id}/resume", response_model=ResumeResponse)
async def resume_session(
    session_id: str, principal: Principal = Depends(require_service_auth)
) -> ResumeResponse:
    session = await _session_or_404(session_id)
    try:
        result = await ResumeManager(session).resume()
    except RuntimeError as exc:
        raise _error(ErrorCode.VOICE_SESSION_INVALID_STATE, str(exc), status.HTTP_409_CONFLICT) from exc
    return ResumeResponse(
        session_id=session_id, state=session.state.state.value, resumed_from=result.get("resumed_from")
    )


@router.post("/voice/session/{session_id}/language", response_model=SimpleResponse)
async def change_language(
    session_id: str, payload: LanguageChangeRequest, principal: Principal = Depends(require_service_auth)
) -> SimpleResponse:
    session = await _session_or_404(session_id)
    result = await session.change_language(
        payload.language, getattr(payload, "dialect", None)
    )
    return SimpleResponse(
        session_id=session_id, state=session.state.state.value, detail=f"language={result['language']}"
    )


@router.post("/voice/session/{session_id}/level", response_model=SimpleResponse)
async def change_level(
    session_id: str, payload: LevelChangeRequest, principal: Principal = Depends(require_service_auth)
) -> SimpleResponse:
    """Re-pitch the same lesson for another level; nothing learned is lost."""
    session = await _session_or_404(session_id)
    result = await session.change_level(payload.level)
    return SimpleResponse(
        session_id=session_id,
        state=session.state.state.value,
        detail=f"level={result['student_level']}",
    )


@router.post("/voice/session/{session_id}/pause", response_model=SimpleResponse)
async def pause_session(
    session_id: str, principal: Principal = Depends(require_service_auth)
) -> SimpleResponse:
    session = await _session_or_404(session_id)
    await session.pause()
    return SimpleResponse(session_id=session_id, state=session.state.state.value, detail="paused")


@router.post("/voice/session/{session_id}/end", response_model=SimpleResponse)
async def end_session(
    session_id: str, principal: Principal = Depends(require_service_auth)
) -> SimpleResponse:
    session = await _session_or_404(session_id)
    await session.end()
    token_store.revoke_session(session_id)
    await get_manager().dispose(session_id)
    return SimpleResponse(session_id=session_id, state="ended", detail="ended")


@router.get("/voice/students/{student_id}/latest")
async def latest_session(
    student_id: str, principal: Principal = Depends(require_service_auth)
) -> dict[str, Any]:
    """What a returning student would resume (§28)."""
    state = await get_manager().latest_for_student(student_id)
    if state is None:
        return {"found": False}
    return {"found": True, **ResumeManager.restore_plan(state)}


# --------------------------------------------------------------------------- #
# capabilities and health
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# curriculum: what the tutor can teach
# --------------------------------------------------------------------------- #


@router.get("/curriculum/courses")
async def curriculum_courses(
    with_topics: bool = True,
    principal: Principal = Depends(require_service_auth),
) -> dict[str, Any]:
    """The course catalogue and, by default, every topic inside each course.

    The client picks a `topic_id` from here and passes it to
    `POST /voice/session`, which turns the topic into the tutor's lesson plan.
    """
    courses = curriculum.list_courses(with_topics=with_topics)
    return {"courses": courses, "count": len(courses), "stats": curriculum.stats()}


@router.get("/curriculum/topics")
async def curriculum_topics(
    course_id: str | None = None,
    level: str | None = None,
    principal: Principal = Depends(require_service_auth),
) -> dict[str, Any]:
    topics = curriculum.list_topics()
    if course_id:
        topics = [t for t in topics if t["course_id"] == course_id]
    if level:
        topics = [t for t in topics if t["level"] == level]
    return {"topics": topics, "count": len(topics)}


@router.get("/curriculum/topics/{topic_id}")
async def curriculum_topic(
    topic_id: str, principal: Principal = Depends(require_service_auth)
) -> dict[str, Any]:
    topic = curriculum.get_topic(topic_id)
    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown topic '{topic_id}'"
        )
    course = curriculum.get_course(topic.course_id)
    return {
        "topic": topic.as_dict(),
        "course": course.as_dict(with_topics=False) if course else None,
    }


class UploadMaterial(BaseModel):
    """Uploaded course material for a lesson built from the student's own content (§4)."""
    title: str
    text: str
    student_id: str | None = None
    language: str | None = None


@router.post("/voice/material")
async def upload_material(body: UploadMaterial, request: Request) -> dict[str, Any]:
    """Ingest a student's uploaded course material so a typed topic gets a grounded lesson.

    Returns the document id; send it back in the WS `start` frame as `document_ids` to teach
    from this material (round 26)."""
    from app.rag import local_corpus
    document_id = local_corpus.add_document(
        title=body.title, text=body.text, student_id=body.student_id, language=body.language,
    )
    chunks = local_corpus.retrieve(body.title or "", document_ids=[document_id], top_k=50)
    logger.info("[material] ingested %s title=%r chars=%d chunks=%d", document_id, body.title,
                len(body.text or ""), len(chunks))
    return {
        "document_id": document_id,
        "title": body.title,
        "chunks": len(chunks),
        "chars": len(body.text or ""),
    }


@router.get("/voice/languages")
async def languages() -> dict[str, Any]:
    """Static capability documentation: what each language can route to,
    independent of which credentials happen to be configured here."""
    from app.providers.capabilities import PROVIDER_CAPABILITIES
    from app.voice.provider_router import VoiceProviderRouter

    router_ = VoiceProviderRouter(available_providers=tuple(PROVIDER_CAPABILITIES))
    out = []
    for code in SUPPORTED_LANGUAGES:
        plans = router_.plan_pipelines(code, respect_health=False)
        entry = {
            "code": code,
            "name": LANGUAGE_NAMES[code],
            "primary_pipeline": plans[0].as_dict() if plans else None,
            "fallback_pipelines": [p.as_dict() for p in plans[1:4]],
            "realtime_native": any(p.pipeline.mode == "realtime" for p in plans),
        }
        if code == "ar":
            # Arabic is one language but two registers: the student picks which
            # one the tutor *sounds* like (see app/voice/dialects.py).
            entry["dialects"] = arabic_dialect_options()
        out.append(entry)
        continue
        out.append(  # pragma: no cover - unreachable, kept for shape reference
            {
                "code": code,
                "name": LANGUAGE_NAMES[code],
                "primary_pipeline": plans[0].as_dict() if plans else None,
                "fallback_pipelines": [p.as_dict() for p in plans[1:4]],
                "realtime_native": any(p.pipeline.mode == "realtime" for p in plans),
            }
        )
    return {"languages": out, "count": len(out)}


@router.get("/voice/voices")
async def demo_voices() -> dict[str, Any]:
    """The voices the offline demo can speak with (server-side key only).

    The browser is never given the vendor key: it asks this service, which holds
    the key, for a list of voices to choose from. Without a key the endpoint says
    so (503) instead of returning an empty list that looks like a bug.
    """
    settings = get_settings()
    vendor = demo_voice_vendor(settings)
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No real voice is configured for the demo. Set ELEVENLABS_API_KEY "
                "(free plan works) and VOICE_DEMO_VOICE=elevenlabs, or keep the "
                "browser voice."
            ),
        )
    from app.providers.elevenlabs.voices import list_voices

    try:
        voices = await list_voices(settings)
    except Exception as exc:  # noqa: BLE001 - vendor/transport problem, not a bug here
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        detail = (
            f"ElevenLabs refused the request ({status_code or 'no response'})."
            if status_code
            else "Could not reach ElevenLabs from this host."
        )
        if status_code in (401, 403):
            detail += " Check the API key (free plan keys work)."
        logger.warning("listing demo voices failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc
    return {
        "provider": vendor,
        "model": settings.elevenlabs_tts_model,
        "default_voice_id": settings.elevenlabs_voice_id,
        "voices": voices,
    }


@health_router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        provider_mode=settings.voice_provider_mode,
        mock_providers=settings.voice_enable_mock_providers,
        live_model=settings.active_gemini_live_model,
        gemini_auth=settings.gemini_auth_mode,
        live_models={
            "vertex": settings.gemini_vertex_live_model,
            "developer_api": settings.gemini_live_model,
        },
        demo_voice=demo_voice_label(settings),
    )


@health_router.get("/health/providers")
async def provider_health(principal: Principal = Depends(require_service_auth)) -> dict[str, Any]:
    from app.voice.provider_router import VoiceProviderRouter

    settings = get_settings()
    manager = get_manager()
    bridge = get_bridge()
    await bridge.ensure_ready()
    router_ = VoiceProviderRouter()
    return {
        "status": "ok",
        "service": settings.service_name,
        "mode": settings.voice_provider_mode,
        "configured_providers": sorted(settings.configured_providers()),
        "routing": router_.describe(),
        "capabilities": {
            name: {
                "realtime": sorted(cap.realtime),
                "stt": sorted(cap.stt),
                "tts": sorted(cap.tts),
                "llm": sorted(cap.llm),
                "streaming_stt": cap.streaming_stt,
                "streaming_tts": cap.streaming_tts,
                "turn_detection": cap.turn_detection,
                "native_interruption": cap.native_interruption,
                "tool_calling": cap.tool_calling,
                "notes": cap.notes,
            }
            for name, cap in PROVIDER_CAPABILITIES.items()
        },
        "matrix": capability_matrix(),
        "lerna": bridge.status(),
        "persistence": manager.repository.backend,
        "active_sessions": manager.active_count(),
    }
