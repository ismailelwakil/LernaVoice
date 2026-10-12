"""Service authentication (§37) and ephemeral client tokens (§40).

The LERNA backend authenticates to this service with a shared service key
(`X-Voice-Service-Key` or `Authorization: Bearer`). It then mints a short-lived
session token for the browser, so neither the service key nor any *provider*
credential ever reaches a client.
"""

from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Query, status

from app.config import Settings, get_settings
from app.voice.events import ErrorCode

TOKEN_TTL_SECONDS = 900


@dataclass(frozen=True)
class Principal:
    kind: str  # "service" | "session" | "anonymous"
    session_id: str | None = None


class SessionTokenStore:
    """In-process store of single-use-ish session tokens (15 min TTL)."""

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[str, float]] = {}

    def issue(self, session_id: str, ttl: int = TOKEN_TTL_SECONDS) -> dict[str, object]:
        token = f"vst_{secrets.token_urlsafe(32)}"
        expires = time.time() + ttl
        self._tokens[token] = (session_id, expires)
        self._gc()
        return {"token": token, "expires_at": expires, "expires_in": ttl, "session_id": session_id}

    def resolve(self, token: str) -> str | None:
        entry = self._tokens.get(token)
        if entry is None:
            return None
        session_id, expires = entry
        if time.time() > expires:
            self._tokens.pop(token, None)
            return None
        return session_id

    def revoke(self, token: str) -> None:
        self._tokens.pop(token, None)

    def revoke_session(self, session_id: str) -> None:
        for token, (sid, _) in list(self._tokens.items()):
            if sid == session_id:
                self._tokens.pop(token, None)

    def _gc(self) -> None:
        now = time.time()
        for token, (_, expires) in list(self._tokens.items()):
            if expires < now:
                self._tokens.pop(token, None)


token_store = SessionTokenStore()


def _matches(candidate: str | None, expected: str | None) -> bool:
    if not candidate or not expected:
        return False
    return hmac.compare_digest(candidate.strip(), expected.strip())


def _unauthorised() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "event": "error",
            "code": ErrorCode.VOICE_AUTH_REQUIRED.value,
            "message": "Valid service credentials are required.",
            "recoverable": False,
        },
    )


def require_service_auth(
    x_voice_service_key: str | None = Header(default=None, alias="X-Voice-Service-Key"),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Principal:
    s = settings
    expected = s.voice_service_api_key
    if not expected:
        # No shared key configured: there is nothing to verify against. Requiring auth
        # with a *blank* key would lock out every caller — including this service's own
        # console — so treat "auth required but no key" as a misconfiguration and run
        # open (a startup warning is logged). Once a key is set, auth is enforced.
        return Principal(kind="anonymous")

    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:]
    if _matches(x_voice_service_key, expected) or _matches(bearer, expected):
        return Principal(kind="service")
    raise _unauthorised()


def authenticate_websocket(
    session_id: str,
    *,
    token: str | None,
    service_key: str | None,
    settings: Settings | None = None,
) -> Principal:
    """WS clients present either a session token or the service key."""
    s = settings or get_settings()
    if token:
        resolved = token_store.resolve(token)
        if resolved == session_id:
            return Principal(kind="session", session_id=session_id)
        raise _unauthorised()
    expected = s.voice_service_api_key
    if not expected:
        return Principal(kind="anonymous", session_id=session_id)
    if _matches(service_key, expected):
        return Principal(kind="service", session_id=session_id)
    raise _unauthorised()


def websocket_credentials(
    token: str | None = Query(default=None),
    x_voice_service_key: str | None = Header(default=None, alias="X-Voice-Service-Key"),
) -> tuple[str | None, str | None]:
    return token, x_voice_service_key
