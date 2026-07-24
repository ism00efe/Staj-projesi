"""Application service — the single entry point the UI (or any client) calls.

This is the composition root: it wires concrete implementations (embeddings, vector
store, LLM provider) into the ``RAGEngine`` via constructor injection. All business logic
lives behind ``AssistantService``; the UI must not reach past it.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import Settings, get_settings
from .llm import build_llm_provider
from .models import Answer
from .observability import new_trace_id, start_metrics_server
from .rag import (
    ChromaVectorStore,
    CrossEncoderReranker,
    DenseRetriever,
    HybridRetriever,
    RAGEngine,
    Retriever,
    SentenceTransformerEmbeddings,
    build_bm25_from_corpus,
)

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
        """Convenience for UIs that hand over an uploaded file path.

        SECURITY: rejects files above ``MAX_UPLOAD_BYTES`` before reading them, so an
        oversized upload cannot exhaust memory/CPU in sanitize/chunk/embed. This is a
        second, defense-in-depth layer alongside ``RAGEngine``'s own ``log_text`` cap.
        """

        log_text = None
        if file_path:
            path = Path(file_path)
            if path.stat().st_size > self._settings.max_upload_bytes:
                trace_id = new_trace_id()
                logger.warning(
                    "upload rejected: file too large",
                    extra={"trace_id": trace_id, "step": "upload", "status": "rejected"},
                )
                limit_mb = self._settings.max_upload_bytes // 1_000_000
                return Answer(
                    text=f"Yüklenen dosya çok büyük (limit: {limit_mb} MB).",
                    citations=[],
                    retrieved=[],
                    trace_id=trace_id,
                )
            log_text = path.read_text(encoding="utf-8", errors="replace")
        return self.ask(question, log_text)

    def knowledge_base_size(self) -> int:
        return self._engine.corpus_size()


def build_retriever(
    settings: Settings,
    embedder,
    store,
    *,
    hybrid: bool | None = None,
    rerank: bool | None = None,
) -> Retriever:
    """Assemble the retrieval chain: dense (+ BM25 sparse) (+ cross-encoder re-rank).

    ``hybrid`` / ``rerank`` default to the settings values; the evaluation script overrides
    them to compare strategies side by side.
    """

    hybrid = settings.hybrid_enabled if hybrid is None else hybrid
    rerank = settings.rerank_enabled if rerank is None else rerank

    dense = DenseRetriever(embedder, store)
    if not hybrid and not rerank:
        return dense

    sparse = None
    if hybrid:
        try:
            sparse = build_bm25_from_corpus(
                settings.corpus_dir,
                chunk_size=settings.chunk_size,
                overlap=settings.chunk_overlap,
                k1=settings.bm25_k1,
                b=settings.bm25_b,
            )
        except FileNotFoundError:
            # Degrade gracefully rather than taking the app down: dense still works.
            logger.warning(
                "Corpus '%s' not found; sparse retrieval disabled.", settings.corpus_dir
            )

    reranker = CrossEncoderReranker(settings.reranker_model) if rerank else None
    return HybridRetriever(
        dense,
        sparse,
        reranker,
        rrf_k=settings.rrf_k,
        candidates=settings.rerank_candidates,
    )


def build_service(settings: Settings | None = None) -> AssistantService:
    """Construct a fully-wired :class:`AssistantService` from settings."""

    settings = settings or get_settings()
    logger.info(
        "Building service (LLM=%s, hybrid=%s, rerank=%s, guard=%s, metrics=%s)...",
        settings.llm_provider,
        settings.hybrid_enabled,
        settings.rerank_enabled,
        settings.input_guard_enabled,
        settings.metrics_enabled,
    )

    if settings.metrics_enabled:
        start_metrics_server(settings.metrics_port)

    embedder = SentenceTransformerEmbeddings(settings.embedding_model)
    store = ChromaVectorStore(settings.chroma_persist_dir, settings.chroma_collection)
    llm = build_llm_provider(settings)
    retriever = build_retriever(settings, embedder, store)
    engine = RAGEngine(
        embedder,
        store,
        llm,
        top_k=settings.top_k,
        retriever=retriever,
        input_guard_enabled=settings.input_guard_enabled,
    )

    return AssistantService(engine, settings)
