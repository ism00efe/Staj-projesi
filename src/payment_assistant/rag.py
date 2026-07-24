"""The RAG engine: the heart of the pipeline.

Orchestrates the online query path:
    sanitize -> (optional) log summary -> embed query -> retrieve -> prompt -> generate
    -> map citations.

Depends only on the small interfaces (``EmbeddingProvider``, ``VectorStore``,
``LLMProvider``), never on concrete SDKs — so any of them can be swapped independently.
"""

from __future__ import annotations

import logging
import re

from .embeddings import EmbeddingProvider
from .llm.base import LLMProvider
from .logs import summarize_log
from .models import Answer, Citation, RetrievedChunk
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .sanitization import sanitize_text
from .vectorstore import VectorStore

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"\[S(\d+)\]")


class RAGEngine:
    """Retrieval-augmented generation over the payment knowledge base."""

    def __init__(
        self,
        embedder: EmbeddingProvider,
        store: VectorStore,
        llm: LLMProvider,
        *,
        top_k: int = 4,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._llm = llm
        self._top_k = top_k

    def corpus_size(self) -> int:
        """Number of indexed chunks currently searchable."""

        return self._store.count()

    def answer(self, question: str, log_text: str | None = None) -> Answer:
        """Answer a question, optionally grounded by an uploaded log."""

        # 1) SECURITY: sanitize every user-supplied input before it goes anywhere.
        clean_question, q_red = sanitize_text(question or "")
        redaction_labels = [f"{r.label}×{r.count}" for r in q_red]

        log_summary = ""
        if log_text:
            # SECURITY: sanitize the RAW log first (the guaranteed gate), then summarize
            # the already-clean text. This does not rely on the summarizer's field
            # allowlist to keep PII out, and it lets us report what was actually masked.
            clean_log, l_red = sanitize_text(log_text)
            redaction_labels += [f"{r.label}×{r.count}" for r in l_red]
            log_summary = summarize_log(clean_log)

        # 2) Build the retrieval query (question + salient log fields).
        retrieval_query = clean_question.strip()
        if log_summary:
            retrieval_query = (
                f"{retrieval_query}\nLog: {log_summary}"
                if retrieval_query
                else f"Log: {log_summary}"
            )
        if not retrieval_query:
            return Answer(
                text="Lütfen bir soru yazın veya bir log dosyası yükleyin.",
                citations=[],
                retrieved=[],
                redactions=redaction_labels,
            )

        # 3) Retrieve.
        if self._store.count() == 0:
            return Answer(
                text=(
                    "Bilgi tabanı boş görünüyor. Lütfen önce "
                    "`python scripts/ingest.py` komutunu çalıştırın."
                ),
                citations=[],
                retrieved=[],
                redactions=redaction_labels,
            )

        query_vec = self._embedder.embed_query(retrieval_query)
        retrieved = self._store.query(query_vec, self._top_k)

        # 4) Generate a grounded answer.
        user_prompt = build_user_prompt(retrieval_query, retrieved)
        text = self._llm.generate(SYSTEM_PROMPT, user_prompt)

        # 5) Map the [S#] tags the model actually used back to their sources.
        citations = self._extract_citations(text, retrieved)

        return Answer(
            text=text,
            citations=citations,
            retrieved=retrieved,
            redactions=redaction_labels,
        )

    @staticmethod
    def _extract_citations(
        text: str, retrieved: list[RetrievedChunk]
    ) -> list[Citation]:
        used = sorted({int(m) for m in _TAG_RE.findall(text)})
        citations: list[Citation] = []
        for idx in used:
            if 1 <= idx <= len(retrieved):
                item = retrieved[idx - 1]
                c = item.chunk
                citations.append(
                    Citation(
                        tag=f"S{idx}",
                        document_id=c.document_id,
                        title=c.title,
                        doc_type=c.doc_type,
                        source_path=c.source_path,
                        score=item.score,
                    )
                )
        return citations
