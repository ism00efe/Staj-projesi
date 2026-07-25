"""Local LLM via Ollama's HTTP API (the default provider)."""

from __future__ import annotations

import logging

import requests

from .base import LLMError

logger = logging.getLogger(__name__)


class OllamaProvider:
    """Calls a local Ollama server's ``/api/chat`` endpoint."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        timeout: int = 180,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout

    @property
    def name(self) -> str:
        return f"ollama:{self._model}"

    def generate(self, system: str, user: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": self._max_tokens,
            },
        }
        try:
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json=payload,  # type: ignore[arg-type]
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise LLMError(
                f"Ollama request failed ({self._base_url}). Is `ollama serve` running "
                f"and the model '{self._model}' pulled? Original error: {exc}"
            ) from exc
        try:
            content = data["message"]["content"].strip()
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected Ollama response: {data}") from exc

        # Best-effort token usage logging (Ollama includes it in the non-streaming
        # response). Never changes the return type — logged only, not surfaced.
        token_count = data.get("eval_count")
        prompt_token_count = data.get("prompt_eval_count")
        if token_count is not None or prompt_token_count is not None:
            logger.info(
                "llm usage",
                extra={
                    "status": "ok",
                    "token_count": token_count,
                    "prompt_token_count": prompt_token_count,
                },
            )
        return content
