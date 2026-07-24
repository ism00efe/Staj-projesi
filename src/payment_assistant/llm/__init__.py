"""LLM provider package: interface + factory.

``build_llm_provider(settings)`` is the single place that maps ``LLM_PROVIDER`` to a
concrete implementation. Adding a provider = one new module + one entry here.
"""

from __future__ import annotations

import logging

from ..config import Settings
from .base import LLMError, LLMProvider

logger = logging.getLogger(__name__)


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Instantiate the LLM provider selected by ``settings.llm_provider``."""

    provider = settings.llm_provider.strip().lower()

    if provider == "ollama":
        from .ollama_provider import OllamaProvider

        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

    if provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=settings.anthropic_api_key or "",
            model=settings.anthropic_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

    if provider == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=settings.openai_api_key or "",
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

    raise LLMError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'. "
        "Expected one of: ollama, anthropic, openai."
    )


__all__ = ["LLMProvider", "LLMError", "build_llm_provider"]
