"""LERNA's own LLM pool exposed as a voice-pipeline component (§11, §68).

The Academic OS engine already routes across Gemini / OpenAI / Anthropic / Groq
with evidence grounding. Reusing it here means a cascade keeps tutoring even
when the Gemini *voice* path is unavailable, and keeps the Voice Tutor inside
LERNA's AI ecosystem instead of spawning a second tutor.

Honest limitation: the existing engine's generation call is synchronous and
returns a complete answer, so this component is not token-streaming. It is run
off the event loop in a worker thread and the cascade still streams audio
sentence by sentence, so perceived latency stays acceptable.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, AsyncIterator

from app.lerna_bridge import LernaBridge, LernaUnavailable, get_bridge
from app.providers.base import (
    LLMProvider,
    ProviderEvent,
    ProviderEventType,
    ProviderInternalError,
    ProviderUnsupportedError,
    ToolHandler,
)

_SPLIT = re.compile(r"(?<=[.!?؟。！？])\s+")


class LernaLLMProvider(LLMProvider):
    provider_name = "lerna"

    def __init__(self, bridge: LernaBridge | None = None):
        self.bridge = bridge or get_bridge()
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
        await self.bridge.ensure_ready()
        if self.bridge.mode != "inprocess":
            raise ProviderUnsupportedError(
                "LERNA LLM component requires the in-process Academic OS engine", provider="lerna"
            )
        tutor = getattr(self.bridge.module, "tutor", None)
        llms = getattr(tutor, "llms", None) or {}
        llm = next(iter(llms.values()), None)
        if llm is None or not hasattr(llm, "generate_prompt"):
            raise ProviderInternalError("no LERNA LLM provider is configured", provider="lerna")

        user_block = "\n".join(
            f"{'Student' if m.get('role') == 'user' else 'Tutor'}: {m.get('content', '')}"
            for m in messages[-10:]
            if m.get("content")
        )
        try:
            text = await asyncio.to_thread(llm.generate_prompt, system_instruction, user_block)
        except LernaUnavailable as exc:
            raise ProviderUnsupportedError(str(exc), provider="lerna") from exc
        except Exception as exc:
            raise ProviderInternalError(f"{type(exc).__name__}: {exc}", provider="lerna") from exc

        answer = (text or "").strip()
        for sentence in _SPLIT.split(answer):
            if self._cancelled:
                return
            if sentence.strip():
                yield ProviderEvent(
                    type=ProviderEventType.OUTPUT_TRANSCRIPT, text=sentence.strip() + " ", partial=True
                )
                await asyncio.sleep(0)
        yield ProviderEvent(type=ProviderEventType.TURN_COMPLETE, text=answer)
