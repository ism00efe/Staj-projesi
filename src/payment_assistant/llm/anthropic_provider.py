"""Anthropic Claude via the Messages HTTP API.

Uses ``requests`` (not the vendor SDK) to keep dependencies minimal and the three
providers symmetric. Selected with ``LLM_PROVIDER=anthropic``.
"""

from __future__ import annotations

import logging

import requests

from .base import LLMError

logger = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


class AnthropicProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        timeout: int = 120,
    ) -> None:
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set but LLM_PROVIDER=anthropic.")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout

    @property
    def name(self) -> str:
        return f"anthropic:{self._model}"

    def generate(self, system: str, user: str) -> str:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        try:
            resp = requests.post(
                _API_URL, headers=headers, json=payload, timeout=self._timeout
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise LLMError(f"Anthropic request failed: {exc}") from exc
        try:
            content = "".join(
                block["text"] for block in data["content"] if block.get("type") == "text"
            ).strip()
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected Anthropic response: {data}") from exc

        # Best-effort token usage logging. Never changes the return type.
        usage = data.get("usage") or {}
        if usage:
            logger.info(
                "llm usage",
                extra={
                    "status": "ok",
                    "token_count": usage.get("output_tokens"),
                    "prompt_token_count": usage.get("input_tokens"),
                },
            )
        return content
