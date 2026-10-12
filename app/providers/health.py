"""Provider health tracking and lightweight circuit breaker (§56, §57)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from app.providers.base import ErrorClass, ProviderError


class HealthState(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    UNSUPPORTED = "unsupported"


@dataclass
class ProviderHealth:
    provider: str
    state: HealthState = HealthState.AVAILABLE
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    last_error: str | None = None
    last_error_class: str | None = None
    cooldown_until: float = 0.0
    last_change: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "last_error_class": self.last_error_class,
            "cooldown_remaining": max(0.0, round(self.cooldown_until - time.time(), 2)),
        }


class ProviderHealthRegistry:
    """Tracks failures per vendor and opens a circuit after N in a row.

    The circuit is never permanent: after `cooldown` seconds the provider moves
    to DEGRADED and is retried (half-open).
    """

    def __init__(self, *, failure_threshold: int = 3, cooldown: float = 60.0, clock=time.time):
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown = cooldown
        self._clock = clock
        self._providers: dict[str, ProviderHealth] = {}

    # ------------------------------------------------------------------ core

    def get(self, provider: str) -> ProviderHealth:
        if provider not in self._providers:
            self._providers[provider] = ProviderHealth(provider=provider)
        return self._providers[provider]

    def record_success(self, provider: str) -> None:
        h = self.get(provider)
        h.consecutive_failures = 0
        h.total_successes += 1
        h.cooldown_until = 0.0
        if h.state is not HealthState.AVAILABLE:
            h.state = HealthState.AVAILABLE
            h.last_change = self._clock()

    def record_failure(self, provider: str, error: ProviderError | Exception) -> HealthState:
        h = self.get(provider)
        h.total_failures += 1
        h.consecutive_failures += 1
        h.last_error = str(error)
        err_class = getattr(error, "error_class", ErrorClass.RECOVERABLE)
        h.last_error_class = err_class.value if isinstance(err_class, ErrorClass) else str(err_class)
        now = self._clock()

        if err_class is ErrorClass.UNSUPPORTED:
            h.state = HealthState.UNSUPPORTED
        elif err_class is ErrorClass.AUTHENTICATION:
            # Do not hammer a bad credential; long cooldown, no retry.
            h.state = HealthState.UNAVAILABLE
            h.cooldown_until = now + max(self.cooldown, 300.0)
        elif err_class in (ErrorClass.RATE_LIMIT, ErrorClass.QUOTA):
            h.state = HealthState.RATE_LIMITED
            h.cooldown_until = now + self.cooldown
        elif h.consecutive_failures >= self.failure_threshold:
            h.state = HealthState.UNAVAILABLE  # circuit open
            h.cooldown_until = now + self.cooldown
        else:
            h.state = HealthState.DEGRADED
        h.last_change = now
        return h.state

    # --------------------------------------------------------------- queries

    def is_available(self, provider: str) -> bool:
        h = self.get(provider)
        now = self._clock()
        if h.state in (HealthState.UNAVAILABLE, HealthState.RATE_LIMITED):
            if now >= h.cooldown_until:
                # half-open: allow a probe
                h.state = HealthState.DEGRADED
                h.consecutive_failures = max(0, self.failure_threshold - 1)
                h.cooldown_until = 0.0
                h.last_change = now
                return True
            return False
        if h.state is HealthState.UNSUPPORTED:
            return False
        return True

    def penalty(self, provider: str) -> int:
        """Lower is better; used to order otherwise-equal candidates."""
        h = self.get(provider)
        return {
            HealthState.AVAILABLE: 0,
            HealthState.DEGRADED: 1,
            HealthState.RATE_LIMITED: 5,
            HealthState.UNAVAILABLE: 10,
            HealthState.UNSUPPORTED: 100,
        }[h.state]

    def mark_unsupported(self, provider: str) -> None:
        h = self.get(provider)
        h.state = HealthState.UNSUPPORTED
        h.last_change = self._clock()

    def reset(self, provider: str | None = None) -> None:
        if provider:
            self._providers.pop(provider, None)
        else:
            self._providers.clear()

    def snapshot(self) -> dict[str, dict]:
        return {name: h.as_dict() for name, h in self._providers.items()}
