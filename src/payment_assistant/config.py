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
    chunk_size: int = Field(default=1200)
    chunk_overlap: int = Field(default=150)
    top_k: int = Field(default=4)

    # --- UI / app -------------------------------------------------------------
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=7860)
    ui_language: str = Field(default="tr")

    # --- Logging --------------------------------------------------------------
    log_level: str = Field(default="INFO")


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance (read the environment once)."""

    return Settings()


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once, with a concise, readable format."""

    resolved = (level or get_settings().log_level).upper()
    logging.basicConfig(
        level=getattr(logging, resolved, logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
