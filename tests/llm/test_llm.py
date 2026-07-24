"""Tests for the LLM provider abstraction: factory, parsing, and error handling.

No real network calls — ``requests.post`` is monkeypatched.
"""

from __future__ import annotations

import pytest
import requests

from payment_assistant.config import Settings
from payment_assistant.llm import build_llm_provider
from payment_assistant.llm.anthropic_provider import AnthropicProvider
from payment_assistant.llm.base import LLMError
from payment_assistant.llm.ollama_provider import OllamaProvider
from payment_assistant.llm.openai_provider import OpenAIProvider


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _settings(**overrides) -> Settings:
    base = dict(llm_provider="ollama", anthropic_api_key=None, openai_api_key=None)
    base.update(overrides)
    return Settings(_env_file=None, **base)


# --- factory ----------------------------------------------------------------
def test_factory_builds_ollama():
    provider = build_llm_provider(_settings(llm_provider="ollama"))
    assert isinstance(provider, OllamaProvider)
    assert provider.name.startswith("ollama:")


def test_factory_builds_anthropic():
    provider = build_llm_provider(_settings(llm_provider="anthropic", anthropic_api_key="k"))
    assert isinstance(provider, AnthropicProvider)


def test_factory_builds_openai():
    provider = build_llm_provider(_settings(llm_provider="openai", openai_api_key="k"))
    assert isinstance(provider, OpenAIProvider)


def test_factory_unknown_provider_raises():
    with pytest.raises(LLMError):
        build_llm_provider(_settings(llm_provider="does-not-exist"))


def test_provider_selection_is_case_insensitive():
    assert isinstance(build_llm_provider(_settings(llm_provider="OLLAMA")), OllamaProvider)


# --- missing credentials ----------------------------------------------------
def test_anthropic_requires_key():
    with pytest.raises(LLMError):
        AnthropicProvider(api_key="", model="m")


def test_openai_requires_key():
    with pytest.raises(LLMError):
        OpenAIProvider(api_key="", model="m")


# --- generate parsing -------------------------------------------------------
def test_ollama_generate_parses_message(monkeypatch):
    monkeypatch.setattr(
        requests, "post", lambda *a, **k: FakeResponse({"message": {"content": " hi "}})
    )
    provider = OllamaProvider("http://x", "m")
    assert provider.generate("sys", "user") == "hi"


def test_anthropic_generate_concatenates_text_blocks(monkeypatch):
    payload = {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    provider = AnthropicProvider(api_key="k", model="m")
    assert provider.generate("sys", "user") == "ab"


def test_openai_generate_parses_choice(monkeypatch):
    payload = {"choices": [{"message": {"content": "answer"}}]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    provider = OpenAIProvider(api_key="k", model="m")
    assert provider.generate("sys", "user") == "answer"


# --- error handling ---------------------------------------------------------
def test_network_error_becomes_llmerror(monkeypatch):
    def boom(*a, **k):
        raise requests.RequestException("connection refused")

    monkeypatch.setattr(requests, "post", boom)
    with pytest.raises(LLMError):
        OllamaProvider("http://x", "m").generate("s", "u")


def test_malformed_response_becomes_llmerror(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse({"unexpected": 1}))
    with pytest.raises(LLMError):
        OpenAIProvider(api_key="k", model="m").generate("s", "u")


def test_ollama_malformed_response(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse({"nope": 1}))
    with pytest.raises(LLMError):
        OllamaProvider("http://x", "m").generate("s", "u")


def test_anthropic_network_error(monkeypatch):
    def boom(*a, **k):
        raise requests.RequestException("timeout")

    monkeypatch.setattr(requests, "post", boom)
    with pytest.raises(LLMError):
        AnthropicProvider(api_key="k", model="m").generate("s", "u")


def test_anthropic_malformed_response(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse({"bad": 1}))
    with pytest.raises(LLMError):
        AnthropicProvider(api_key="k", model="m").generate("s", "u")


def test_openai_network_error(monkeypatch):
    def boom(*a, **k):
        raise requests.RequestException("dns")

    monkeypatch.setattr(requests, "post", boom)
    with pytest.raises(LLMError):
        OpenAIProvider(api_key="k", model="m").generate("s", "u")


def test_provider_names():
    assert OllamaProvider("http://x", "m").name == "ollama:m"
    assert AnthropicProvider(api_key="k", model="m").name == "anthropic:m"
    assert OpenAIProvider(api_key="k", model="m").name == "openai:m"


# --- best-effort token usage logging (never changes the return value) --------
def test_ollama_logs_token_usage_when_present(monkeypatch, caplog):
    import logging

    payload = {"message": {"content": "hi"}, "eval_count": 12, "prompt_eval_count": 34}
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    with caplog.at_level(logging.INFO):
        result = OllamaProvider("http://x", "m").generate("s", "u")
    assert result == "hi"  # return type/value unaffected
    usage_records = [r for r in caplog.records if getattr(r, "token_count", None) == 12]
    assert usage_records and usage_records[0].prompt_token_count == 34


def test_ollama_no_usage_fields_no_log(monkeypatch, caplog):
    import logging

    monkeypatch.setattr(
        requests, "post", lambda *a, **k: FakeResponse({"message": {"content": "hi"}})
    )
    with caplog.at_level(logging.INFO):
        OllamaProvider("http://x", "m").generate("s", "u")
    assert not any(hasattr(r, "token_count") for r in caplog.records)


def test_anthropic_logs_token_usage_when_present(monkeypatch, caplog):
    import logging

    payload = {
        "content": [{"type": "text", "text": "hi"}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    with caplog.at_level(logging.INFO):
        result = AnthropicProvider(api_key="k", model="m").generate("s", "u")
    assert result == "hi"
    usage_records = [r for r in caplog.records if getattr(r, "token_count", None) == 5]
    assert usage_records and usage_records[0].prompt_token_count == 10


def test_openai_logs_token_usage_when_present(monkeypatch, caplog):
    import logging

    payload = {
        "choices": [{"message": {"content": "hi"}}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
    }
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    with caplog.at_level(logging.INFO):
        result = OpenAIProvider(api_key="k", model="m").generate("s", "u")
    assert result == "hi"
    usage_records = [r for r in caplog.records if getattr(r, "token_count", None) == 3]
    assert usage_records and usage_records[0].prompt_token_count == 7
