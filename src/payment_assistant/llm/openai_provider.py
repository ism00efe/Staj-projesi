"""OpenAI (or any OpenAI-compatible endpoint) via the Chat Completions HTTP API.

Uses ``requests`` for symmetry with the other providers. Because it targets the standard
``/v1/chat/completions`` shape, it also works with compatible servers (vLLM, LM Studio,
etc.) by changing ``OPENAI_BASE_URL``. Selected with ``LLM_PROVIDER=openai``.
"""

from __future__ import annotations

import logging

import requests

from .base import LLMError

logger = logging.getLogger(__name__)


class OpenAIProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        temperature: float = 0.1,
        max_tokens: int = 1024,
        timeout: int = 120,
    ) -> None:
        if not api_key:
            raise LLMError("OPENAI_API_KEY is not set but LLM_PROVIDER=openai.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout

    @property
    def name(self) -> str:
        return f"openai:{self._model}"

    def generate(self, system: str, user: str) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = requests.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise LLMError(f"OpenAI request failed: {exc}") from exc
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected OpenAI response: {data}") from exc
