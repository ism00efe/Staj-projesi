"""Application service — the single entry point the UI (or any client) calls.

This is the composition root: it wires concrete implementations (embeddings, vector
store, LLM provider) into the ``RAGEngine`` via constructor injection. All business logic
lives behind ``AssistantService``; the UI must not reach past it.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import Settings, get_settings
from .embeddings import SentenceTransformerEmbeddings
from .llm import build_llm_provider
from .models import Answer
from .rag import RAGEngine
from .vectorstore import ChromaVectorStore

logger = logging.getLogger(__name__)


class AssistantService:
    """Use-case facade: ask a question and/or analyze an uploaded log."""

    def __init__(self, engine: RAGEngine, settings: Settings) -> None:
        self._engine = engine
        self._settings = settings

    def ask(self, question: str | None, log_text: str | None = None) -> Answer:
        """Answer a troubleshooting question, optionally grounded by a log."""

        return self._engine.answer(question or "", log_text)

    def ask_with_log_file(self, question: str | None, file_path: str | None) -> Answer:
        """Convenience for UIs that hand over an uploaded file path."""

        log_text = None
        if file_path:
            log_text = Path(file_path).read_text(encoding="utf-8", errors="replace")
        return self.ask(question, log_text)

    def knowledge_base_size(self) -> int:
        return self._engine.corpus_size()


def build_service(settings: Settings | None = None) -> AssistantService:
    """Construct a fully-wired :class:`AssistantService` from settings."""

    settings = settings or get_settings()
    logger.info("Building service (LLM provider=%s)...", settings.llm_provider)

    embedder = SentenceTransformerEmbeddings(settings.embedding_model)
    store = ChromaVectorStore(settings.chroma_persist_dir, settings.chroma_collection)
    llm = build_llm_provider(settings)
    engine = RAGEngine(embedder, store, llm, top_k=settings.top_k)

    return AssistantService(engine, settings)
