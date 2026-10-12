"""Gemini text LLM component used inside composed pipelines (§11).

This is the reasoning engine for every cascade — including the Igbo pipeline,
where speech is handled by other vendors but the tutoring itself stays Gemini.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from app.config import Settings, get_settings
from app.providers.base import (
    LLMProvider,
    ProviderEvent,
    ProviderEventType,
    ToolHandler,
)
from app.providers.gemini.client import build_genai_client, classify_gemini_error, genai_types


class GeminiLLMProvider(LLMProvider):
    provider_name = "gemini"

    def __init__(self, settings: Settings | None = None, client: Any | None = None):
        self.settings = settings or get_settings()
        self._client = client
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
        try:
            types = genai_types()
            if self._client is None:
                self._client = build_genai_client(self.settings)

            contents = [
                types.Content(
                    role="model" if m.get("role") == "assistant" else "user",
                    parts=[types.Part(text=m.get("content", ""))],
                )
                for m in messages
                if m.get("content")
            ]
            config: dict[str, Any] = {"system_instruction": system_instruction, "temperature": 0.7}
            if tools:
                config["tools"] = [types.Tool(function_declarations=tools)]

            stream = await self._client.aio.models.generate_content_stream(
                model=self.settings.gemini_text_model,
                contents=contents,
                config=types.GenerateContentConfig(**config),
            )
        except Exception as exc:
            raise classify_gemini_error(exc) from exc

        collected: list[str] = []
        try:
            async for chunk in stream:
                if self._cancelled:
                    break
                for call in getattr(chunk, "function_calls", None) or []:
                    name = getattr(call, "name", None)
                    args = dict(getattr(call, "args", {}) or {})
                    if tool_handler and name:
                        await tool_handler(name, args)
                    yield ProviderEvent(type=ProviderEventType.TOOL_CALL, tool_name=name, tool_args=args)
                text = getattr(chunk, "text", None)
                if text:
                    collected.append(text)
                    yield ProviderEvent(type=ProviderEventType.OUTPUT_TRANSCRIPT, text=text, partial=True)
                await asyncio.sleep(0)
        except Exception as exc:
            raise classify_gemini_error(exc) from exc

        yield ProviderEvent(type=ProviderEventType.TURN_COMPLETE, text="".join(collected))
