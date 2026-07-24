"""Retriever abstraction, dense adapter, and hybrid fusion.

Introduces a single ``Retriever`` seam so the engine can be given dense-only, hybrid, or
hybrid+re-ranked retrieval without changing the existing ``VectorStore`` /
``EmbeddingProvider`` abstractions — ``DenseRetriever`` is a thin *adapter* over that
existing pair.

Fusion uses Reciprocal Rank Fusion (RRF):

    score(d) = Σ_r  1 / (k + rank_r(d))

RRF combines rankings, not scores, so it needs no score normalization between a cosine
similarity and a BM25 score — which is exactly why it is the standard choice here.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from ..models import Chunk, RetrievedChunk
from ..observability import instrumented_step
from .embeddings import EmbeddingProvider
from .reranker import Reranker
from .vectorstore import VectorStore

logger = logging.getLogger(__name__)


@runtime_checkable
class Retriever(Protocol):
    """Returns the most relevant chunks for a (already sanitized) query."""

    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]: ...


class DenseRetriever:
    """Adapter exposing the existing embedder + vector store as a ``Retriever``."""

    strategy = "dense"

    def __init__(self, embedder: EmbeddingProvider, store: VectorStore) -> None:
        self._embedder = embedder
        self._store = store

    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        if top_k <= 0:
            return []
        with instrumented_step("embed"):
            query_vector = self._embedder.embed_query(query)
        return self._store.query(query_vector, top_k)


def reciprocal_rank_fusion(
    rankings: list[list[RetrievedChunk]], *, k: int = 60
) -> list[RetrievedChunk]:
    """Fuse several ranked lists into one, scoring each chunk by ``Σ 1/(k + rank)``.

    Ties break on chunk id so the output is fully deterministic.
    """

    scores: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            chunk_id = item.chunk.id
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            chunks.setdefault(chunk_id, item.chunk)

    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [RetrievedChunk(chunk=chunks[cid], score=score) for cid, score in ordered]


class HybridRetriever:
    """dense (+ sparse) -> RRF fuse -> top-N candidates -> optional re-rank -> top_k.

    Each stage is optional: with no ``sparse`` and no ``reranker`` this behaves exactly
    like ``DenseRetriever``, which keeps the dense-only baseline honest.
    """

    def __init__(
        self,
        dense: Retriever,
        sparse: Retriever | None = None,
        reranker: Reranker | None = None,
        *,
        rrf_k: int = 60,
        candidates: int = 20,
    ) -> None:
        self._dense = dense
        self._sparse = sparse
        self._reranker = reranker
        self._rrf_k = rrf_k
        self._candidates = candidates

    @property
    def strategy(self) -> str:
        """Descriptive name for observability labels (e.g. metrics, logs)."""

        if self._sparse is not None and self._reranker is not None:
            return "hybrid+rerank"
        if self._sparse is not None:
            return "hybrid"
        if self._reranker is not None:
            return "dense+rerank"
        return "dense"

    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        if top_k <= 0:
            return []

        # Pull a deeper candidate pool than top_k so fusion/re-ranking have room to work.
        depth = max(self._candidates, top_k)
        rankings = [self._dense.retrieve(query, depth)]
        if self._sparse is not None:
            rankings.append(self._sparse.retrieve(query, depth))

        # With a single ranking there is nothing to fuse; keep the original scores.
        fused = reciprocal_rank_fusion(rankings, k=self._rrf_k) if len(rankings) > 1 else rankings[0]
        # Truncate to `depth`, not `candidates`: a caller asking for more than the
        # configured candidate pool must still receive top_k results.
        candidates = fused[:depth]

        if self._reranker is not None and candidates:
            with instrumented_step("rerank", candidate_count=len(candidates)) as rec:
                result = self._reranker.rerank(query, candidates, top_k)
                rec.set(result_count=len(result))
            return result
        return candidates[:top_k]
