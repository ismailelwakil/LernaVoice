"""Shared helpers for WebSocket/HTTP based providers."""

from __future__ import annotations

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


def classify_status(status: int, message: str, provider: str) -> ProviderError:
    if status in (401, 403):
        return ProviderAuthError(f"{provider} authentication failed ({status}): {message}", provider=provider)
    if status == 429:
        return ProviderRateLimitError(f"{provider} rate limited: {message}", provider=provider)
    if status in (402, 413):
        return ProviderQuotaError(f"{provider} quota/payment issue: {message}", provider=provider)
    if status == 404:
        return ProviderUnsupportedError(f"{provider} resource not found: {message}", provider=provider)
    if status in (408, 504):
        return ProviderTimeoutError(f"{provider} timeout: {message}", provider=provider)
    if 500 <= status < 600:
        return ProviderInternalError(f"{provider} server error ({status}): {message}", provider=provider)
    return ProviderInternalError(f"{provider} error ({status}): {message}", provider=provider)


def classify_exception(exc: Exception, provider: str) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, TimeoutError):
        return ProviderTimeoutError(f"{provider} timed out", provider=provider)
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is None:
        status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return classify_status(status, str(exc), provider)
    message = f"{type(exc).__name__}: {exc}"
    low = message.lower()
    if "quota" in low or "payment" in low:
        return ProviderQuotaError(message, provider=provider)
    if "rate" in low and "limit" in low:
        return ProviderRateLimitError(message, provider=provider)
    if "unauthor" in low or "forbidden" in low or "api key" in low or "api_key" in low:
        return ProviderAuthError(message, provider=provider)
    if "timeout" in low or "timed out" in low:
        return ProviderTimeoutError(message, provider=provider)
    if any(t in low for t in ("connect", "closed", "handshake", "dns", "websocket", "reset")):
        return ProviderNetworkError(message, provider=provider)
    return ProviderInternalError(message, provider=provider)


def require_websockets():
    try:
        import websockets  # type: ignore

        return websockets
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ProviderInternalError("the 'websockets' package is required", provider="unknown") from exc
