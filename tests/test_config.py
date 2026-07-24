"""Tests for configuration loading."""

from __future__ import annotations

import logging

from payment_assistant.config import Settings, configure_logging, get_settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.llm_provider == "ollama"
    assert s.ollama_model == "qwen2.5:7b-instruct"
    assert s.embedding_model == "intfloat/multilingual-e5-small"
    assert s.top_k == 4
    assert s.chunk_size == 500  # finer chunks so re-ranking has a real candidate pool
    assert s.chunk_overlap == 80


def test_retrieval_defaults():
    s = Settings(_env_file=None)
    assert s.hybrid_enabled is True  # BM25 fusion is cheap; on by default
    assert s.rerank_enabled is True  # +64% MRR (measured); see DECISIONS.md D15
    assert s.reranker_model.startswith("BAAI/bge-reranker")  # must be multilingual
    assert s.rerank_candidates == 20
    assert s.rrf_k == 60


def test_retrieval_env_override(monkeypatch):
    monkeypatch.setenv("HYBRID_ENABLED", "false")
    monkeypatch.setenv("RERANK_ENABLED", "true")
    monkeypatch.setenv("RERANK_CANDIDATES", "50")
    s = Settings(_env_file=None)
    assert s.hybrid_enabled is False
    assert s.rerank_enabled is True
    assert s.rerank_candidates == 50


def test_observability_and_security_defaults():
    s = Settings(_env_file=None)
    assert s.log_format == "json"  # structured logs by default
    assert s.metrics_enabled is False  # collection is free; the HTTP server is opt-in
    assert s.metrics_port == 9090
    assert s.input_guard_enabled is True  # cheap regex guard; safe default is ON
    assert s.max_upload_bytes == 2_000_000


def test_observability_and_security_env_override(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "text")
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("METRICS_PORT", "9999")
    monkeypatch.setenv("INPUT_GUARD_ENABLED", "false")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1000")
    s = Settings(_env_file=None)
    assert s.log_format == "text"
    assert s.metrics_enabled is True
    assert s.metrics_port == 9999
    assert s.input_guard_enabled is False
    assert s.max_upload_bytes == 1000


def test_env_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("TOP_K", "9")
    s = Settings(_env_file=None)
    assert s.llm_provider == "openai"
    assert s.top_k == 9


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_configure_logging_sets_level():
    configure_logging(level="WARNING")
    assert logging.getLogger().level == logging.WARNING
    configure_logging(level="INFO")  # reset so other tests aren't muffled


def test_configure_logging_json_format_installs_json_formatter():
    from payment_assistant.observability.logging_context import JsonFormatter

    configure_logging(level="INFO", log_format="json")
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, JsonFormatter)
    configure_logging(level="INFO", log_format="json")  # reset default for other tests


def test_configure_logging_text_format_installs_plain_formatter():
    from payment_assistant.observability.logging_context import JsonFormatter

    configure_logging(level="INFO", log_format="text")
    handler = logging.getLogger().handlers[0]
    assert not isinstance(handler.formatter, JsonFormatter)
    assert "trace_id" in handler.formatter._fmt
    configure_logging(level="INFO", log_format="json")  # reset default for other tests


def test_configure_logging_attaches_trace_id_filter():
    from payment_assistant.observability.logging_context import TraceIdFilter

    configure_logging()
    handler = logging.getLogger().handlers[0]
    assert any(isinstance(f, TraceIdFilter) for f in handler.filters)
