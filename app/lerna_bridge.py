"""Bridge to the existing LERNA / Academic OS AI engine (§1, §29-§31, §68).

The Voice Tutor is a *modality* inside LERNA, not a second AI system. This
module is the single place that knows how to reach the existing engine:

  * inprocess  - import `src.integration.service.build_module()` from
                 `ai-service/` and call the real RAG, Progress Profile and
                 Learning Orchestrator objects.
  * http       - call the deployed LERNA Integration API facade.
  * disabled   - no LERNA available (clearly reported, never silently faked).

All engine calls are synchronous, so they are dispatched to a worker thread to
keep the realtime event loop free (§3).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.logging_setup import get_logger

log = get_logger(__name__)


def _candidate_paths(settings: Settings) -> list[Path]:
    paths = []
    if settings.lerna_ai_service_path:
        paths.append(Path(settings.lerna_ai_service_path))
    here = Path(__file__).resolve()
    # voice-ai/app/lerna_bridge.py -> repo root is two levels up from voice-ai
    for base in (here.parents[2], here.parents[3] if len(here.parents) > 3 else here.parents[2]):
        paths.append(base / "ai-service")
    return paths


class LernaBridge:
    """Thin, lazy, failure-tolerant handle on the LERNA engine."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.mode: str = "uninitialised"
        self._module: Any = None
        self._http: Any = None
        self._init_error: str | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------- lifecycle

    async def ensure_ready(self) -> None:
        if self.mode != "uninitialised":
            return
        async with self._lock:
            if self.mode != "uninitialised":
                return
            wanted = self.settings.lerna_integration_mode
            if wanted == "disabled":
                self.mode = "disabled"
                return
            if wanted in ("auto", "inprocess"):
                if await asyncio.to_thread(self._try_inprocess):
                    self.mode = "inprocess"
                    log.info("LERNA engine loaded in-process")
                    return
                if wanted == "inprocess":
                    self.mode = "disabled"
                    return
            if wanted in ("auto", "http") and self.settings.lerna_backend_url:
                import httpx

                headers = {}
                if self.settings.lerna_backend_api_key:
                    headers["Authorization"] = f"Bearer {self.settings.lerna_backend_api_key}"
                self._http = httpx.AsyncClient(
                    base_url=self.settings.lerna_backend_url.rstrip("/"), headers=headers, timeout=20.0
                )
                self.mode = "http"
                log.info("LERNA engine reachable over HTTP")
                return
            self.mode = "disabled"
            log.warning("LERNA engine unavailable; RAG and Progress Profile are disabled", extra={"reason": self._init_error})

    def _try_inprocess(self) -> bool:
        for path in _candidate_paths(self.settings):
            if not (path / "src" / "integration" / "service.py").exists():
                continue
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
            try:
                from src.integration.service import build_module  # type: ignore

                data_dir = str(path / "data")
                self._module = build_module(data_dir=data_dir)
                return True
            except Exception as exc:
                self._init_error = f"{type(exc).__name__}: {exc}"
                log.warning("in-process LERNA import failed", extra={"path": str(path), "error_type": type(exc).__name__})
        if self._init_error is None:
            self._init_error = "ai-service package not found"
        return False

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    @property
    def available(self) -> bool:
        return self.mode in ("inprocess", "http")

    def status(self) -> dict[str, Any]:
        return {"mode": self.mode, "available": self.available, "error": self._init_error}

    # ----------------------------------------------------------------- calls

    async def call_inprocess(self, method: str, *args: Any, **kwargs: Any) -> Any:
        await self.ensure_ready()
        if self.mode != "inprocess" or self._module is None:
            raise LernaUnavailable(f"in-process LERNA engine not loaded (mode={self.mode})")
        fn = getattr(self._module, method, None)
        if fn is None:
            raise LernaUnavailable(f"LERNA engine has no method '{method}'")
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def call_http(self, method: str, url: str, **kwargs: Any) -> Any:
        await self.ensure_ready()
        if self.mode != "http" or self._http is None:
            raise LernaUnavailable(f"LERNA HTTP facade not configured (mode={self.mode})")
        response = await self._http.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    @property
    def module(self) -> Any:
        return self._module


class LernaUnavailable(RuntimeError):
    pass


_bridge: LernaBridge | None = None


def get_bridge(settings: Settings | None = None) -> LernaBridge:
    global _bridge
    if _bridge is None:
        _bridge = LernaBridge(settings)
    return _bridge


def set_bridge(bridge: LernaBridge | None) -> None:
    global _bridge
    _bridge = bridge
