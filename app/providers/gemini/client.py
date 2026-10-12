"""Shared Gemini client construction and error classification.

Two authentication paths are supported and chosen from configuration (§8):

  * Gemini Developer API — API key, models such as
    `gemini-2.5-flash-native-audio-preview-12-2025` (free tier available).
  * Vertex AI / Agent Platform — Application Default Credentials with a GCP
    project, models such as `gemini-3.8-live`.

The API key never leaves the server; clients receive ephemeral service tokens
instead (see app/api/security.py).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderInternalError,
    ProviderNetworkError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnsupportedError,
)

_AUTH_TOKENS = ("api key", "unauthenticated", "permission denied", "401", "403", "invalid_argument: api key")
_RATE_TOKENS = ("rate limit", "429", "resource_exhausted", "too many requests")
_QUOTA_TOKENS = ("quota", "billing", "exceeded your current quota")
_TIMEOUT_TOKENS = ("timeout", "timed out", "deadline exceeded")
_NETWORK_TOKENS = ("connection", "unreachable", "dns", "reset by peer", "websocket")
_UNSUPPORTED_TOKENS = ("not supported", "unsupported", "not found for api version", "404")


def classify_gemini_error(exc: Exception, provider: str = "gemini") -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, TimeoutError):
        return ProviderTimeoutError(str(exc) or "gemini timeout", provider=provider)
    message = f"{type(exc).__name__}: {exc}"
    low = message.lower()
    if any(t in low for t in _QUOTA_TOKENS):
        return ProviderQuotaError(message, provider=provider)
    if any(t in low for t in _RATE_TOKENS):
        return ProviderRateLimitError(message, provider=provider)
    if any(t in low for t in _AUTH_TOKENS):
        return ProviderAuthError(message, provider=provider)
    if any(t in low for t in _TIMEOUT_TOKENS):
        return ProviderTimeoutError(message, provider=provider)
    if any(t in low for t in _UNSUPPORTED_TOKENS):
        return ProviderUnsupportedError(message, provider=provider)
    if any(t in low for t in _NETWORK_TOKENS):
        return ProviderNetworkError(message, provider=provider)
    return ProviderInternalError(message, provider=provider)


def build_genai_client(settings: Settings | None = None) -> Any:
    s = settings or get_settings()
    try:
        from google import genai  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ProviderInternalError(
            "google-genai is not installed; run pip install google-genai", provider="gemini"
        ) from exc

    if s.google_genai_use_vertexai:
        if not s.google_cloud_project:
            raise ProviderAuthError(
                "GOOGLE_GENAI_USE_VERTEXAI=true requires GOOGLE_CLOUD_PROJECT", provider="gemini"
            )
        credentials = _vertex_credentials(s)
        kwargs: dict[str, Any] = {
            "vertexai": True,
            "project": s.google_cloud_project,
            "location": s.google_cloud_location,
        }
        if credentials is not None:
            kwargs["credentials"] = credentials
        return genai.Client(**kwargs)
    if not s.gemini_api_key:
        raise ProviderAuthError("GEMINI_API_KEY is not configured", provider="gemini")
    return genai.Client(api_key=s.gemini_api_key)


def _vertex_credentials(settings: Settings) -> Any:
    """Service-account credentials from configuration, or None to use ADC.

    `GOOGLE_APPLICATION_CREDENTIALS` in `.env` is visible to *our* settings but not to the
    Google SDK (which reads the process environment) — and a missing credential then
    surfaces as a confusing "default credentials were not found" instead of the real
    problem. Loading the file here makes the configured path authoritative.
    """
    path = settings.google_application_credentials or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not path:
        return None
    if not Path(path).exists():
        raise ProviderAuthError(
            f"GOOGLE_APPLICATION_CREDENTIALS points at a file that does not exist: {path}",
            provider="gemini",
        )
    try:
        from google.oauth2 import service_account  # type: ignore
    except ImportError:  # pragma: no cover - google-auth ships with google-genai
        return None
    try:
        return service_account.Credentials.from_service_account_file(
            path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except Exception as exc:  # noqa: BLE001 - re-raised as a classified provider error
        raise ProviderAuthError(
            f"the service-account file could not be loaded: {type(exc).__name__}", provider="gemini"
        ) from exc


def genai_types() -> Any:
    try:
        from google.genai import types  # type: ignore

        return types
    except ImportError as exc:  # pragma: no cover
        raise ProviderInternalError("google-genai is not installed", provider="gemini") from exc
