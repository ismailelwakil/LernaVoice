"""OpenRouter — an OpenAI-compatible LLM gateway (round 25).

Used as an alternative / fallback *brain* for composed pipelines: OpenRouter
generates the tutor's words, a speech vendor (Azure) speaks them. It is never a
voice provider itself.
"""

from app.providers.openrouter.llm import OpenRouterLLMProvider

__all__ = ["OpenRouterLLMProvider"]
