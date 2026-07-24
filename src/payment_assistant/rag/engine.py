"""The RAG engine: the heart of the pipeline.

Orchestrates the online query path:
    sanitize -> (optional) log summary -> guard -> retrieve -> prompt -> generate
    -> map citations.

Depends only on the small interfaces (``EmbeddingProvider``, ``VectorStore``,
``LLMProvider``), never on concrete SDKs — so any of them can be swapped independently.

Every call is wrapped in a bound ``trace_id`` (see ``observability.bind_trace_id``) and
each stage is timed/logged/metriced via ``instrumented_step`` — nested layers (the
retriever's embed/rerank steps) pick the same trace_id up automatically through the
context var, with no change to their own signatures.
"""

from __future__ import annotations

import logging
import re

from ..llm.base import LLMProvider
from ..models import Answer, Citation, RetrievedChunk
from ..observability import (
    REQUEST_COUNT,
    RETRIEVER_STRATEGY,
    bind_trace_id,
    instrumented_step,
    record_redactions,
)
from ..sanitization import sanitize_text
from ..security import REFUSAL_MESSAGE, inspect_query
from .embeddings import EmbeddingProvider
from .logs import summarize_log
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .retriever import DenseRetriever, Retriever
from .vectorstore import VectorStore

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"\[S(\d+)\]")

# Defense-in-depth cap on log_text length, independent of any file-size check a caller
# (e.g. the service layer's upload handling) may already apply — protects any direct
# caller of `answer()`/`ask()`, not just the file-upload path.
_MAX_LOG_CHARS = 500_000


class RAGEngine:
    """Retrieval-augmented generation over the payment knowledge base."""

    def __init__(
        self,
        embedder: EmbeddingProvider,
        store: VectorStore,
        llm: LLMProvider,
        *,
        top_k: int = 4,
        retriever: Retriever | None = None,
        input_guard_enabled: bool = True,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._llm = llm
        self._top_k = top_k
        # Default to plain dense retrieval; the composition root injects a
        # HybridRetriever when sparse/re-ranking are enabled.
        self._retriever = retriever or DenseRetriever(embedder, store)
        self._input_guard_enabled = input_guard_enabled

    def corpus_size(self) -> int:
        """Number of indexed chunks currently searchable."""

        return self._store.count()

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """Retrieve the most relevant chunks for an already-sanitized query."""

        return self._retriever.retrieve(query, top_k or self._top_k)

    def answer(
        self, question: str, log_text: str | None = None, trace_id: str | None = None
    ) -> Answer:
        """Answer a question, optionally grounded by an uploaded log.

        ``trace_id`` may be supplied by the caller (e.g. a future API layer); otherwise
        one is generated and bound for the duration of this call.
        """

        with bind_trace_id(trace_id) as tid:
            return self._answer(question, log_text, tid)

    def _answer(self, question: str, log_text: str | None, trace_id: str) -> Answer:
        if log_text and len(log_text) > _MAX_LOG_CHARS:
            log_text = log_text[:_MAX_LOG_CHARS]

        # 1) SECURITY: sanitize every user-supplied input before it goes anywhere.
        with instrumented_step("sanitize") as rec:
            clean_question, q_red = sanitize_text(question or "")
            redaction_labels = [f"{r.label}×{r.count}" for r in q_red]
            record_redactions(q_red)

            log_summary = ""
            if log_text:
                # SECURITY: sanitize the RAW log first (the guaranteed gate), then
                # summarize the already-clean text. This does not rely on the
                # summarizer's field allowlist to keep PII out, and it lets us report
                # what was actually masked.
                clean_log, l_red = sanitize_text(log_text)
                redaction_labels += [f"{r.label}×{r.count}" for r in l_red]
                record_redactions(l_red)
                log_summary = summarize_log(clean_log)
            rec.set(redaction_count=len(redaction_labels))

        # 2) Build the retrieval query (question + salient log fields).
        retrieval_query = clean_question.strip()
        if log_summary:
            retrieval_query = (
                f"{retrieval_query}\nLog: {log_summary}"
                if retrieval_query
                else f"Log: {log_summary}"
            )
        if not retrieval_query:
            REQUEST_COUNT.labels(status="empty").inc()
            return Answer(
                text="Lütfen bir soru yazın veya bir log dosyası yükleyin.",
                citations=[],
                retrieved=[],
                redactions=redaction_labels,
                trace_id=trace_id,
            )

        # 3) SECURITY: block prompt-injection attempts before retrieval or the LLM ever
        # see the query. Runs on the already-sanitized text, so nothing logged here can
        # contain raw PII.
        if self._input_guard_enabled:
            safe, reason = inspect_query(retrieval_query)
            if not safe:
                logger.warning(
                    "query blocked by input guard",
                    extra={"reason": reason, "status": "blocked"},
                )
                REQUEST_COUNT.labels(status="blocked").inc()
                return Answer(
                    text=REFUSAL_MESSAGE,
                    citations=[],
                    retrieved=[],
                    redactions=redaction_labels,
                    trace_id=trace_id,
                )

        # 4) Retrieve.
        if self._store.count() == 0:
            REQUEST_COUNT.labels(status="empty_kb").inc()
            return Answer(
                text=(
                    "Bilgi tabanı boş görünüyor. Lütfen önce "
                    "`python scripts/ingest.py` komutunu çalıştırın."
                ),
                citations=[],
                retrieved=[],
                redactions=redaction_labels,
                trace_id=trace_id,
            )

        with instrumented_step("retrieve") as rec:
            retrieved = self.retrieve(retrieval_query)
            rec.set(chunk_count=len(retrieved))
        RETRIEVER_STRATEGY.labels(
            strategy=getattr(self._retriever, "strategy", "custom")
        ).inc()

        # 5) Generate a grounded answer.
        with instrumented_step("generate"):
            user_prompt = build_user_prompt(retrieval_query, retrieved)
            text = self._llm.generate(SYSTEM_PROMPT, user_prompt)

        # 6) Map the [S#] tags the model actually used back to their sources.
        with instrumented_step("cite") as rec:
            citations = self._extract_citations(text, retrieved)
            rec.set(citation_count=len(citations))

        REQUEST_COUNT.labels(status="ok").inc()
        return Answer(
            text=text,
            citations=citations,
            retrieved=retrieved,
            redactions=redaction_labels,
            trace_id=trace_id,
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
