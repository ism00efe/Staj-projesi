"""Tests for the retriever abstraction, RRF fusion, and the hybrid chain."""

from __future__ import annotations

from payment_assistant.models import RetrievedChunk
from payment_assistant.rag.retriever import (
    DenseRetriever,
    HybridRetriever,
    reciprocal_rank_fusion,
)
from tests.conftest import FakeEmbeddings, FakeReranker, FakeRetriever, FakeVectorStore, make_chunk


def _ranked(*doc_ids: str) -> list[RetrievedChunk]:
    return [RetrievedChunk(make_chunk(d), 1.0) for d in doc_ids]


# --- DenseRetriever adapter -------------------------------------------------
def test_dense_retriever_embeds_then_queries():
    embedder = FakeEmbeddings()
    store = FakeVectorStore([make_chunk("a"), make_chunk("b", 1)])
    results = DenseRetriever(embedder, store).retrieve("soru", 2)

    assert embedder.query_calls == ["soru"]
    assert [r.chunk.document_id for r in results] == ["a", "b"]


def test_dense_retriever_top_k_zero():
    assert DenseRetriever(FakeEmbeddings(), FakeVectorStore()).retrieve("q", 0) == []


# --- Reciprocal Rank Fusion -------------------------------------------------
def test_rrf_rewards_agreement_across_rankings():
    """A document ranked well by BOTH retrievers beats one ranked first by only one."""
    dense = _ranked("only_dense", "agreed")
    sparse = _ranked("only_sparse", "agreed")

    fused = reciprocal_rank_fusion([dense, sparse], k=60)
    assert fused[0].chunk.document_id == "agreed"


def test_rrf_scores_match_hand_computation():
    dense = _ranked("x", "y")
    sparse = _ranked("y")
    fused = reciprocal_rank_fusion([dense, sparse], k=60)

    scores = {r.chunk.document_id: r.score for r in fused}
    # x: only dense at rank 1 -> 1/61 ; y: dense rank 2 + sparse rank 1 -> 1/62 + 1/61
    assert scores["x"] == 1 / 61
    assert scores["y"] == 1 / 62 + 1 / 61
    assert fused[0].chunk.document_id == "y"  # higher fused score wins


def test_rrf_k_dampens_rank_differences():
    dense = _ranked("first", "second")
    small_k = reciprocal_rank_fusion([dense], k=1)
    large_k = reciprocal_rank_fusion([dense], k=1000)
    # A large k flattens the gap between rank 1 and rank 2.
    small_gap = small_k[0].score - small_k[1].score
    large_gap = large_k[0].score - large_k[1].score
    assert large_gap < small_gap


def test_rrf_deduplicates_chunks():
    fused = reciprocal_rank_fusion([_ranked("a"), _ranked("a")], k=60)
    assert len(fused) == 1
    assert fused[0].score == 2 * (1 / 61)


def test_rrf_empty_input():
    assert reciprocal_rank_fusion([], k=60) == []
    assert reciprocal_rank_fusion([[], []], k=60) == []


def test_rrf_is_deterministic_on_ties():
    # Identical rankings in both lists -> equal scores -> tie broken by chunk id.
    fused = reciprocal_rank_fusion([_ranked("b", "a"), _ranked("a", "b")], k=60)
    assert [r.chunk.id for r in fused] == sorted(r.chunk.id for r in fused)


# --- HybridRetriever --------------------------------------------------------
def test_hybrid_without_sparse_behaves_like_dense():
    dense = FakeRetriever([make_chunk("a"), make_chunk("b", 1)])
    hybrid = HybridRetriever(dense, sparse=None, reranker=None, candidates=20)
    results = hybrid.retrieve("q", 2)
    assert [r.chunk.document_id for r in results] == ["a", "b"]
    # Scores are untouched when there is nothing to fuse.
    assert results[0].score == 1.0


def test_hybrid_fuses_both_sources():
    dense = FakeRetriever([make_chunk("dense_only"), make_chunk("shared", 1)])
    sparse = FakeRetriever([make_chunk("shared", 1), make_chunk("sparse_only")])
    hybrid = HybridRetriever(dense, sparse, candidates=20)

    results = hybrid.retrieve("q", 3)
    ids = [r.chunk.document_id for r in results]
    assert ids[0] == "shared"  # agreed-upon document ranks first
    assert set(ids) == {"shared", "dense_only", "sparse_only"}


def test_hybrid_requests_deeper_candidate_pool_than_top_k():
    dense = FakeRetriever([make_chunk(f"d{i}", i) for i in range(30)])
    HybridRetriever(dense, candidates=20).retrieve("q", 3)
    # It must fetch `candidates` deep, not just top_k, so fusion/re-ranking have room.
    assert dense.calls[0][1] == 20


def test_hybrid_applies_reranker_and_truncates():
    dense = FakeRetriever([make_chunk("a"), make_chunk("b", 1), make_chunk("c", 2)])
    reranker = FakeReranker(preferred_order=["c::2", "a::0", "b::1"])
    hybrid = HybridRetriever(dense, reranker=reranker, candidates=20)

    results = hybrid.retrieve("q", 2)
    assert [r.chunk.document_id for r in results] == ["c", "a"]
    query, n_candidates, top_k = reranker.calls[0]
    assert query == "q" and n_candidates == 3 and top_k == 2


def test_hybrid_skips_reranker_when_no_candidates():
    reranker = FakeReranker()
    hybrid = HybridRetriever(FakeRetriever([]), reranker=reranker, candidates=20)
    assert hybrid.retrieve("q", 3) == []
    assert reranker.calls == []  # never invoked on an empty candidate set


def test_hybrid_top_k_zero():
    dense = FakeRetriever([make_chunk("a")])
    assert HybridRetriever(dense).retrieve("q", 0) == []
    assert dense.calls == []


def test_hybrid_honors_top_k_larger_than_candidate_pool():
    """Asking for more results than `candidates` must still return top_k, not `candidates`."""
    dense = FakeRetriever([make_chunk(f"d{i}", i) for i in range(30)])
    results = HybridRetriever(dense, candidates=5).retrieve("q", 12)
    assert len(results) == 12


def test_hybrid_survives_one_empty_retriever():
    dense = FakeRetriever([make_chunk("a")])
    sparse = FakeRetriever([])  # sparse finds nothing
    results = HybridRetriever(dense, sparse, candidates=20).retrieve("q", 3)
    assert [r.chunk.document_id for r in results] == ["a"]


# --- strategy labels (used for observability) --------------------------------
def test_dense_retriever_strategy_label():
    assert DenseRetriever(FakeEmbeddings(), FakeVectorStore()).strategy == "dense"


def test_hybrid_strategy_label_dense_only():
    assert HybridRetriever(FakeRetriever([])).strategy == "dense"


def test_hybrid_strategy_label_hybrid():
    hybrid = HybridRetriever(FakeRetriever([]), sparse=FakeRetriever([]))
    assert hybrid.strategy == "hybrid"


def test_hybrid_strategy_label_dense_plus_rerank():
    hybrid = HybridRetriever(FakeRetriever([]), reranker=FakeReranker())
    assert hybrid.strategy == "dense+rerank"


def test_hybrid_strategy_label_hybrid_plus_rerank():
    hybrid = HybridRetriever(
        FakeRetriever([]), sparse=FakeRetriever([]), reranker=FakeReranker()
    )
    assert hybrid.strategy == "hybrid+rerank"
