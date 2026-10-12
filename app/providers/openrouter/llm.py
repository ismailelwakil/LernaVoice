"""OpenRouter text-LLM component for composed pipelines (round 25).

OpenAI-compatible chat-completions with server-sent streaming. Only the *words*
come from OpenRouter; speech is handled by a TTS vendor (Azure) in the cascade.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from app.config import Settings, get_settings
from app.providers.base import (
    LLMProvider,
    ProviderAuthError,
    ProviderEvent,
    ProviderEventType,
    ProviderInternalError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ToolHandler,
)

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def _classify(status: int, body: str, provider: str = "openrouter") -> Exception:
    if status in (401, 403):
        return ProviderAuthError(f"OpenRouter auth failed ({status})", provider=provider)
    if status == 429:
        return ProviderRateLimitError(f"OpenRouter rate-limited ({status})", provider=provider)
    if status >= 500:
        return ProviderInternalError(f"OpenRouter upstream error ({status})", provider=provider)
    return ProviderNetworkError(f"OpenRouter error {status}: {body[:200]}", provider=provider)


class OpenRouterLLMProvider(LLMProvider):
    provider_name = "openrouter"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._cancelled = False

    async def cancel(self) -> None:
        self._cancelled = True

    async def stream_reply(
        self,
        messages: list[dict[str, str]],
        *,
        system_instruction: str,
        language: str,
        tools: list[dict[str, Any]] | None = None,
        tool_handler: ToolHandler | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        self._cancelled = False
        if not self.settings.openrouter_api_key:
            raise ProviderAuthError("OPENROUTER_API_KEY is not configured", provider="openrouter")

        payload: dict[str, Any] = {
            "model": self.settings.openrouter_model,
            "stream": True,
            "temperature": 0.7,
            "messages": [{"role": "system", "content": system_instruction}]
            + [
                {"role": "assistant" if m.get("role") == "assistant" else "user", "content": m.get("content", "")}
                for m in messages
                if m.get("content")
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "X-Title": "LERNA Voice AI",
        }

        collected: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                async with client.stream("POST", _ENDPOINT, json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode("utf-8", "replace")
                        raise _classify(resp.status_code, body)
                    async for line in resp.aiter_lines():
                        if self._cancelled:
                            break
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                        text = delta.get("content") or ""
                        if text:
                            collected.append(text)
                            yield ProviderEvent(
                                type=ProviderEventType.OUTPUT_TRANSCRIPT, text=text, partial=True
                            )
                        await asyncio.sleep(0)
        except httpx.HTTPError as exc:
            raise ProviderNetworkError(f"OpenRouter network error: {exc}", provider="openrouter") from exc

        yield ProviderEvent(type=ProviderEventType.TURN_COMPLETE, text="".join(collected))
