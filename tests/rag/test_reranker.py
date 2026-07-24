"""Tests for the cross-encoder re-ranker.

``sentence_transformers.CrossEncoder`` is monkeypatched so no model is downloaded.
"""

from __future__ import annotations

import sentence_transformers

from payment_assistant.models import RetrievedChunk
from payment_assistant.rag.reranker import CrossEncoderReranker
from tests.conftest import make_chunk


class FakeCrossEncoder:
    """Scores a pair by how many query tokens appear in the document text."""

    instances: list[str] = []

    def __init__(self, model_name, device=None):
        FakeCrossEncoder.instances.append(model_name)
        self.model_name = model_name

    def predict(self, pairs):
        return [
            float(sum(1 for token in query.lower().split() if token in text.lower()))
            for query, text in pairs
        ]


def _patch(monkeypatch):
    FakeCrossEncoder.instances = []
    monkeypatch.setattr(sentence_transformers, "CrossEncoder", FakeCrossEncoder)


def _candidates() -> list[RetrievedChunk]:
    # Deliberately in the "wrong" order so re-ranking has to fix it.
    return [
        RetrievedChunk(make_chunk("irrelevant", text="webhook signature hmac"), 0.9),
        RetrievedChunk(make_chunk("relevant", text="gateway timeout retry policy"), 0.5),
    ]


def test_rerank_reorders_by_cross_encoder_score(monkeypatch):
    _patch(monkeypatch)
    reranker = CrossEncoderReranker("fake/model")
    results = reranker.rerank("gateway timeout", _candidates(), top_k=2)

    assert [r.chunk.document_id for r in results] == ["relevant", "irrelevant"]
    assert results[0].score == 2.0  # both query tokens matched


def test_rerank_truncates_to_top_k(monkeypatch):
    _patch(monkeypatch)
    results = CrossEncoderReranker("fake/model").rerank("gateway", _candidates(), top_k=1)
    assert len(results) == 1
    assert results[0].chunk.document_id == "relevant"


def test_model_is_lazily_loaded(monkeypatch):
    _patch(monkeypatch)
    reranker = CrossEncoderReranker("fake/model")
    assert FakeCrossEncoder.instances == []  # not loaded at construction
    reranker.rerank("q", _candidates(), top_k=1)
    assert FakeCrossEncoder.instances == ["fake/model"]


def test_model_loaded_only_once(monkeypatch):
    _patch(monkeypatch)
    reranker = CrossEncoderReranker("fake/model")
    reranker.rerank("q", _candidates(), top_k=1)
    reranker.rerank("q2", _candidates(), top_k=1)
    assert len(FakeCrossEncoder.instances) == 1  # cached across calls


def test_empty_candidates_short_circuits(monkeypatch):
    _patch(monkeypatch)
    reranker = CrossEncoderReranker("fake/model")
    assert reranker.rerank("q", [], top_k=3) == []
    assert FakeCrossEncoder.instances == []  # never even loads the model


def test_top_k_zero(monkeypatch):
    _patch(monkeypatch)
    assert CrossEncoderReranker("fake/model").rerank("q", _candidates(), top_k=0) == []


def test_ties_break_deterministically(monkeypatch):
    _patch(monkeypatch)
    # Neither document contains the query token -> both score 0.0 -> tie on chunk id.
    candidates = [
        RetrievedChunk(make_chunk("zeta", text="nothing"), 0.1),
        RetrievedChunk(make_chunk("alpha", text="nothing"), 0.2),
    ]
    results = CrossEncoderReranker("fake/model").rerank("absent", candidates, top_k=2)
    assert [r.chunk.id for r in results] == ["alpha::0", "zeta::0"]
