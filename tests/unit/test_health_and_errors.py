"""Provider health, circuit breaker and error classification (§19, §56, §57)."""

from __future__ import annotations

from app.providers.base import (
    ErrorClass,
    ProviderAuthError,
    ProviderInternalError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnsupportedError,
)
from app.providers.health import HealthState, ProviderHealthRegistry


def test_error_classification():
    assert ProviderTimeoutError("x").error_class is ErrorClass.TEMPORARY
    assert ProviderRateLimitError("x").error_class is ErrorClass.RATE_LIMIT
    assert ProviderAuthError("x").error_class is ErrorClass.AUTHENTICATION
    assert ProviderUnsupportedError("x").error_class is ErrorClass.UNSUPPORTED
    assert ProviderQuotaError("x").error_class is ErrorClass.QUOTA


def test_retry_policy_by_error_type():
    assert ProviderTimeoutError("x").retryable is True
    assert ProviderRateLimitError("x").retryable is True
    assert ProviderAuthError("x").retryable is False  # §20: never loop on auth
    assert ProviderUnsupportedError("x").retryable is False
    assert ProviderQuotaError("x").retryable is False


def test_circuit_opens_after_threshold_and_is_not_permanent():
    now = [1000.0]
    registry = ProviderHealthRegistry(failure_threshold=3, cooldown=60.0, clock=lambda: now[0])

    for _ in range(2):
        registry.record_failure("gemini", ProviderInternalError("boom"))
    assert registry.get("gemini").state is HealthState.DEGRADED
    assert registry.is_available("gemini")

    registry.record_failure("gemini", ProviderInternalError("boom"))
    assert registry.get("gemini").state is HealthState.UNAVAILABLE
    assert not registry.is_available("gemini")

    now[0] += 61  # cooldown elapsed -> half open
    assert registry.is_available("gemini")
    registry.record_success("gemini")
    assert registry.get("gemini").state is HealthState.AVAILABLE


def test_auth_failure_gets_a_long_cooldown():
    now = [0.0]
    registry = ProviderHealthRegistry(failure_threshold=3, cooldown=10.0, clock=lambda: now[0])
    registry.record_failure("elevenlabs", ProviderAuthError("bad key"))
    assert not registry.is_available("elevenlabs")
    now[0] += 11
    assert not registry.is_available("elevenlabs")  # still cooling down
    now[0] += 300
    assert registry.is_available("elevenlabs")


def test_rate_limit_marks_rate_limited():
    registry = ProviderHealthRegistry()
    registry.record_failure("deepgram", ProviderRateLimitError("429"))
    assert registry.get("deepgram").state is HealthState.RATE_LIMITED
    assert registry.snapshot()["deepgram"]["last_error_class"] == "rate_limit"
