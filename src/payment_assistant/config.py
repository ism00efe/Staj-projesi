"""Typed, environment-driven configuration.

A single ``Settings`` object is the one place all knobs live. Values come from the
process environment / a local ``.env`` file (see ``.env.example``). Nothing here is
required to run the local Ollama default.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM provider ---------------------------------------------------------
    llm_provider: str = Field(default="ollama")  # ollama | anthropic | openai
    llm_temperature: float = Field(default=0.1)
    llm_max_tokens: int = Field(default=1024)

    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="qwen2.5:7b-instruct")

    anthropic_api_key: str | None = Field(default=None)
    anthropic_model: str = Field(default="claude-sonnet-5")

    openai_api_key: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-4o-mini")
    openai_base_url: str = Field(default="https://api.openai.com/v1")

    # --- Embeddings -----------------------------------------------------------
    embedding_model: str = Field(default="intfloat/multilingual-e5-small")

    # --- Vector store ---------------------------------------------------------
    chroma_persist_dir: str = Field(default="./data/chroma")
    chroma_collection: str = Field(default="payment_kb")

    # --- Corpus & retrieval ---------------------------------------------------
    corpus_dir: str = Field(default="./data/corpus")
    chunk_size: int = Field(default=500)
    chunk_overlap: int = Field(default=80)
    top_k: int = Field(default=4)

    # --- Hybrid retrieval (dense + sparse BM25, fused with RRF) ---------------
    hybrid_enabled: bool = Field(default=True)
    rrf_k: int = Field(default=60)
    bm25_k1: float = Field(default=1.5)
    bm25_b: float = Field(default=0.75)

    # --- Cross-encoder re-ranking (must be multilingual) -----------------------
    # Default True: with GPU-accelerated (CUDA) torch this runs in ~0.13s/query
    # (measured), a 64% MRR gain over dense-only. On CPU-only torch it costs ~6s/query
    # instead — set this to false if torch has no CUDA build. See DECISIONS.md D15.
    rerank_enabled: bool = Field(default=True)
    reranker_model: str = Field(default="BAAI/bge-reranker-v2-m3")
    rerank_candidates: int = Field(default=20)

    # --- UI / app -------------------------------------------------------------
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=7860)
    ui_language: str = Field(default="tr")

    # --- HTTP API -------------------------------------------------------------
    # Whole-request cap, enforced before the body is read. Deliberately larger than
    # MAX_UPLOAD_BYTES: the log text is JSON-escaped inside the request body, so the
    # envelope is always bigger than the payload it carries.
    api_max_body_bytes: int = Field(default=5_000_000)  # 5 MB

    # Per-process, best-effort rate limiting. Not a substitute for a reverse proxy in a
    # multi-replica deployment — see DECISIONS.md D23.
    api_rate_limit_enabled: bool = Field(default=True)
    api_rate_limit_requests: int = Field(default=30)
    api_rate_limit_window_seconds: float = Field(default=60.0)

    # How many reverse-proxy hops to trust in X-Forwarded-For. 0 (the default) means the
    # header is ignored entirely and the socket peer is used. Only raise this when a
    # proxy you control actually sits in front of the app: every hop you trust is one an
    # attacker can forge to evade the rate limit.
    api_trusted_proxy_hops: int = Field(default=0)

    # --- Logging ----------------------------------------------------------
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")  # json | text

    # --- Metrics (Prometheus) ----------------------------------------------
    metrics_enabled: bool = Field(default=False)
    metrics_port: int = Field(default=9090)

    # --- Security: prompt injection guard -----------------------------------
    input_guard_enabled: bool = Field(default=True)

    # --- Security: upload limits ---------------------------------------------
    max_upload_bytes: int = Field(default=2_000_000)  # 2 MB


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance (read the environment once)."""

    return Settings()


def configure_logging(level: str | None = None, log_format: str | None = None) -> None:
    """Configure root logging once.

    ``log_format="json"`` (the default) emits structured, machine-parseable log lines
    with a propagated ``trace_id`` — see ``observability.logging_context``.
    ``log_format="text"`` keeps the original human-readable console format, useful for
    interactive debugging.
    """

    settings = get_settings()
    resolved_level = (level or settings.log_level).upper()
    resolved_format = (log_format or settings.log_format).lower()

    # Local import: keeps config.py free of the observability import at module load
    # time (config is imported by nearly every module; observability is not).
    from .observability.logging_context import JsonFormatter, TraceIdFilter

    handler = logging.StreamHandler()
    handler.addFilter(TraceIdFilter())
    if resolved_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-7s | %(name)s | [%(trace_id)s] | %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    root = logging.getLogger()
    root.setLevel(getattr(logging, resolved_level, logging.INFO))
    root.handlers = [handler]
