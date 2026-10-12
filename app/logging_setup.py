"""Structured JSON logging with hard secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)

_SECRET_PATTERNS = [
    re.compile(r"sk_[A-Za-z0-9]{8,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{10,}"),
    re.compile(r"AQ\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"mongodb(\+srv)?://[^@\s]+@", re.IGNORECASE),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)[\"'\s:=]+[A-Za-z0-9_\-\.]{6,}"),
]

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}


def redact(value: Any) -> Any:
    """Replace anything that looks like a credential with ***REDACTED***."""
    if isinstance(value, str):
        out = value
        for pattern in _SECRET_PATTERNS:
            out = pattern.sub("***REDACTED***", out)
        return out
    if isinstance(value, dict):
        return {k: ("***REDACTED***" if _is_secret_key(k) else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def _is_secret_key(key: str) -> bool:
    k = str(key).lower()
    return any(tok in k for tok in ("api_key", "apikey", "token", "password", "secret", "authorization", "uri"))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        rid = request_id_var.get()
        sid = session_id_var.get()
        if rid:
            payload["request_id"] = rid
        if sid:
            payload["session_id"] = sid
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = redact(value)
        if record.exc_info:
            payload["exc_type"] = getattr(record.exc_info[0], "__name__", "Exception")
            payload["exc_message"] = redact(str(record.exc_info[1]))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    for noisy in ("httpx", "httpcore", "websockets", "pymongo", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logging.getLogger(name), {})
