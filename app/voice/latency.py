"""Latency instrumentation (§46)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LatencySpan:
    name: str
    started_at: float
    ended_at: float | None = None

    @property
    def ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return round((self.ended_at - self.started_at) * 1000, 2)


@dataclass
class LatencyTracker:
    """Measures the handful of numbers that actually matter for voice UX."""

    _open: dict[str, LatencySpan] = field(default_factory=dict)
    samples: dict[str, list[float]] = field(default_factory=dict)
    last: dict[str, float] = field(default_factory=dict)

    def start(self, name: str) -> None:
        self._open[name] = LatencySpan(name=name, started_at=time.perf_counter())

    def stop(self, name: str) -> float | None:
        span = self._open.pop(name, None)
        if span is None:
            return None
        span.ended_at = time.perf_counter()
        value = span.ms or 0.0
        self.samples.setdefault(name, []).append(value)
        if len(self.samples[name]) > 100:
            self.samples[name] = self.samples[name][-100:]
        self.last[name] = value
        return value

    def is_open(self, name: str) -> bool:
        return name in self._open

    def stop_if_open(self, name: str) -> float | None:
        return self.stop(name) if name in self._open else None

    def record(self, name: str, ms: float) -> None:
        self.samples.setdefault(name, []).append(ms)
        self.last[name] = ms

    def snapshot(self) -> dict[str, Any]:
        out: dict[str, Any] = {"last_ms": dict(self.last), "avg_ms": {}}
        for name, values in self.samples.items():
            if values:
                out["avg_ms"][name] = round(sum(values) / len(values), 2)
        return out


# Canonical span names
SPAN_SPEECH_TO_FIRST_AUDIO = "speech_to_first_audio"
SPAN_TURN_TOTAL = "turn_total"
SPAN_INTERRUPT_TO_STOP = "interrupt_to_playback_stop"
SPAN_RESUME_TO_AUDIO = "resume_to_first_audio"
SPAN_PROVIDER_CONNECT = "provider_connect"
SPAN_RAG = "rag_retrieval"
