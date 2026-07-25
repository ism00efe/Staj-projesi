"""Cross-encoder re-ranking.

A bi-encoder (our embedding model) encodes query and document *independently*, which is
fast but lossy. A cross-encoder scores the (query, document) pair jointly, so it resolves
cases the bi-encoder blurs — e.g. picking the right runbook among several near-identical
ones. It is far more accurate but far more expensive, so it only ever sees the top-N
candidates that fusion already narrowed down.

**Language constraint:** questions are Turkish while the knowledge base is English, so the
model must be multilingual. The default (``BAAI/bge-reranker-v2-m3``, XLM-R based) handles
Turkish→English pairs; an English-only MS-MARCO cross-encoder would score Turkish queries
near-randomly and actively degrade ranking quality.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from ..models import RetrievedChunk

logger = logging.getLogger(__name__)


@runtime_checkable
class Reranker(Protocol):
    """Re-orders candidate chunks for a query and returns the best ``top_k``."""

    def rerank(
        self, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]: ...


class CrossEncoderReranker:
    """Local cross-encoder re-ranker built on ``sentence_transformers.CrossEncoder``.

    The model is loaded lazily on first use (same pattern as
    :class:`~payment_assistant.rag.embeddings.SentenceTransformerEmbeddings`) so importing
    the package stays cheap and tests never touch the network.
    """

    def __init__(self, model_name: str, *, device: str | None = None) -> None:
        self._model_name = model_name
        self._device = device
        self._model = None  # lazily loaded

    def _ensure_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            logger.info("Loading cross-encoder '%s'...", self._model_name)
            self._model = CrossEncoder(self._model_name, device=self._device)
        return self._model

    def rerank(
        self, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        if not candidates or top_k <= 0:
            return []

        model = self._ensure_model()
        pairs = [(query, item.chunk.text) for item in candidates]
        scores = model.predict(pairs)

        rescored = [
            RetrievedChunk(chunk=item.chunk, score=float(score))
            for item, score in zip(candidates, scores, strict=True)
        ]
        # Ties break on chunk id to keep the ordering deterministic.
        rescored.sort(key=lambda r: (-r.score, r.chunk.id))
        return rescored[:top_k]
