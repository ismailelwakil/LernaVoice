"""Realtime WebSocket endpoint (§34).

    WS /voice/session/{session_id}/audio?token=<session token>

Client -> server
    binary frame            raw little-endian 16-bit PCM, 16 kHz, mono
    JSON  {"type": ...}     control messages (see docs/WEBSOCKET_PROTOCOL.md)

Server -> client
    JSON event envelopes    every event in app.voice.events.EventType, with a
                            monotonically increasing `seq` so a reconnecting
                            client can discard duplicates.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.api.security import authenticate_websocket
from app.config import get_settings
from app.logging_setup import get_logger, session_id_var
from app.providers.base import MalformedAudioError
from app.voice.events import ErrorCode, EventType, VoiceEvent, error_event, make_event
from app.voice.interruption_manager import InterruptionManager
from app.voice.resume_manager import ResumeManager
from app.voice.session_manager import VoiceSession, get_manager

log = get_logger(__name__)
ws_router = APIRouter()

CLOSE_UNAUTHORISED = 4401
CLOSE_NOT_FOUND = 4404
CLOSE_INTERNAL = 4500


@ws_router.websocket("/voice/session/{session_id}/audio")
async def voice_audio_socket(websocket: WebSocket, session_id: str) -> None:
    settings = get_settings()
    token = websocket.query_params.get("token")
    service_key = websocket.headers.get("x-voice-service-key") or websocket.query_params.get("service_key")

    try:
        authenticate_websocket(session_id, token=token, service_key=service_key, settings=settings)
    except HTTPException:
        await websocket.close(code=CLOSE_UNAUTHORISED, reason="unauthorised")
        return

    manager = get_manager()
    session = await manager.get(session_id)
    if session is None:
        await websocket.close(code=CLOSE_NOT_FOUND, reason="unknown session")
        return

    await websocket.accept()
    session_id_var.set(session_id)
    queue = session.subscribe()
    sender = asyncio.create_task(_sender_loop(websocket, queue))

    # Replay enough state that a reconnecting client is immediately consistent.
    await _send(
        websocket,
        make_event(
            EventType.SESSION_STATE_CHANGED,
            session_id=session_id,
            from_state=session.state.state.value,
            to_state=session.state.state.value,
            resumed_connection=True,
            last_seq=session._seq,
            pipeline=session.state.active_pipeline.model_dump(),
            checkpoint=session.state.resume_checkpoint.model_dump()
            if session.state.resume_checkpoint
            else None,
        ).to_wire(),
    )

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if (data := message.get("bytes")) is not None:
                await _handle_audio(session, data)
            elif (text := message.get("text")) is not None:
                # A failing control message must not kill the connection.
                try:
                    await _handle_control(session, websocket, text)
                except Exception as exc:
                    log.warning(
                        "control message failed",
                        extra={"error_type": type(exc).__name__, "session_id": session_id},
                    )
                    await session.emit(
                        error_event(
                            ErrorCode.VOICE_INTERNAL_ERROR,
                            f"Could not process that request: {type(exc).__name__}",
                            recoverable=True,
                            session_id=session_id,
                        )
                    )
    except WebSocketDisconnect:
        log.info("websocket disconnected", extra={"session_id": session_id})
    except Exception as exc:
        log.warning("websocket loop error", extra={"error_type": type(exc).__name__})
        with contextlib.suppress(Exception):
            await _send(
                websocket,
                error_event(
                    ErrorCode.VOICE_INTERNAL_ERROR,
                    "The voice connection hit an internal error.",
                    session_id=session_id,
                ).to_wire(),
            )
    finally:
        session.unsubscribe(queue)
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await sender
        if websocket.client_state is not WebSocketState.DISCONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()


async def _sender_loop(websocket: WebSocket, queue: asyncio.Queue[VoiceEvent]) -> None:
    while True:
        event = await queue.get()
        if websocket.client_state is WebSocketState.DISCONNECTED:
            return
        await _send(websocket, event.to_wire())


async def _send(websocket: WebSocket, payload: dict[str, Any]) -> None:
    with contextlib.suppress(Exception):
        await websocket.send_text(json.dumps(payload, ensure_ascii=False, default=str))


async def _handle_audio(session: VoiceSession, data: bytes) -> None:
    try:
        await session.send_audio(data)
    except MalformedAudioError as exc:
        await session.emit(
            error_event(
                ErrorCode.VOICE_AUDIO_MALFORMED,
                str(exc),
                recoverable=True,
                session_id=session.state.session_id,
            )
        )
    except Exception as exc:
        log.warning("audio ingest failed", extra={"error_type": type(exc).__name__})


async def _handle_control(session: VoiceSession, websocket: WebSocket, raw: str) -> None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        await session.emit(
            error_event(
                ErrorCode.VOICE_AUDIO_MALFORMED,
                "control messages must be JSON",
                session_id=session.state.session_id,
            )
        )
        return

    kind = str(message.get("type", "")).lower()

    if kind == "ping":
        await _send(websocket, make_event(EventType.PONG, session_id=session.state.session_id).to_wire())
        return

    if kind == "start":
        recap = message.get("recap")
        await session.start(recap=None if recap is None else bool(recap))
        return

    if kind == "audio":  # base64 fallback for clients without binary frames
        payload = message.get("audio") or message.get("data") or ""
        try:
            await session.send_audio(base64.b64decode(payload))
        except Exception:
            await session.emit(
                error_event(
                    ErrorCode.VOICE_AUDIO_MALFORMED,
                    "audio payload is not valid base64 PCM16",
                    session_id=session.state.session_id,
                )
            )
        return

    if kind == "audio_start":
        await session.emit(make_event(EventType.AUDIO_INPUT_STARTED, session_id=session.state.session_id))
        return

    if kind == "audio_end":
        await session.emit(make_event(EventType.AUDIO_INPUT_ENDED, session_id=session.state.session_id))
        return

    if kind == "text":
        await session.send_text(str(message.get("text", "")))
        return

    if kind == "interrupt":
        await InterruptionManager(session).interrupt(source=str(message.get("source", "student")))
        return

    if kind == "question":
        await InterruptionManager(session).ask(str(message.get("text", "")))
        return

    if kind == "resume":
        await ResumeManager(session).resume()
        return

    if kind == "language":
        # `language` may carry an Arabic register too (`ar-MSA`), and clients that
        # prefer to be explicit can send `dialect` on its own.
        await session.change_language(
            str(message.get("language", "en")), message.get("dialect")
        )
        return

    if kind == "pause":
        await session.pause()
        return

    if kind == "unpause":
        await session.unpause()
        return

    if kind == "end":
        await session.end(reason="client_request")
        return

    await session.emit(
        error_event(
            ErrorCode.VOICE_SESSION_INVALID_STATE,
            f"unknown control message '{kind}'",
            session_id=session.state.session_id,
        )
    )
