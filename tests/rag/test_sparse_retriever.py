"""Tests for the hand-rolled BM25 sparse retriever."""

from __future__ import annotations

from payment_assistant.rag.sparse_retriever import (
    BM25Retriever,
    build_bm25_from_corpus,
    tokenize,
)
from tests.conftest import make_chunk


# --- tokenizer --------------------------------------------------------------
def test_tokenize_lowercases_and_splits():
    assert tokenize("Gateway TIMEOUT occurred") == ["gateway", "timeout", "occurred"]


def test_tokenize_splits_error_codes():
    # The numeric part is what makes an error code discriminative for BM25.
    assert tokenize("PAY-6006") == ["pay", "6006"]


def test_tokenize_preserves_turkish_characters():
    assert tokenize("ödeme başarısız") == ["ödeme", "başarısız"]


def test_tokenize_empty():
    assert tokenize("") == []


# --- retrieval --------------------------------------------------------------
def _corpus() -> list[BM25Retriever]:
    return [
        make_chunk("doc_1001", text="Error PAY-1001 insufficient funds issuer decline"),
        make_chunk("doc_6006", text="Error PAY-6006 gateway timeout retry with idempotency"),
        make_chunk("doc_webhook", text="Webhook signature verification uses HMAC SHA256"),
    ]


def test_exact_error_code_ranks_first():
    retriever = BM25Retriever(_corpus())
    results = retriever.retrieve("PAY-6006", top_k=3)
    assert results[0].chunk.document_id == "doc_6006"


def test_lexical_match_on_distinct_term():
    retriever = BM25Retriever(_corpus())
    results = retriever.retrieve("HMAC signature", top_k=3)
    assert results[0].chunk.document_id == "doc_webhook"


def test_only_matching_documents_returned():
    retriever = BM25Retriever(_corpus())
    results = retriever.retrieve("webhook", top_k=10)
    # Non-matching docs score 0 and are excluded entirely.
    assert [r.chunk.document_id for r in results] == ["doc_webhook"]


def test_no_match_returns_empty():
    retriever = BM25Retriever(_corpus())
    assert retriever.retrieve("kubernetes helm chart", top_k=5) == []


def test_top_k_limits_results():
    retriever = BM25Retriever(_corpus())
    assert len(retriever.retrieve("error pay", top_k=1)) == 1


def test_top_k_zero_or_negative():
    retriever = BM25Retriever(_corpus())
    assert retriever.retrieve("error", top_k=0) == []


def test_empty_corpus_is_safe():
    retriever = BM25Retriever([])
    assert retriever.count() == 0
    assert retriever.retrieve("anything", top_k=5) == []


def test_scores_are_positive_and_descending():
    retriever = BM25Retriever(_corpus())
    results = retriever.retrieve("error pay timeout", top_k=3)
    scores = [r.score for r in results]
    assert all(s > 0 for s in scores)
    assert scores == sorted(scores, reverse=True)


def test_rarer_term_outranks_common_term():
    """IDF should favour the document matching the rare term."""
    chunks = [
        make_chunk("common_a", text="payment payment payment"),
        make_chunk("common_b", text="payment payment payment"),
        make_chunk("rare", text="payment chargeback"),
    ]
    results = BM25Retriever(chunks).retrieve("payment chargeback", top_k=3)
    assert results[0].chunk.document_id == "rare"


# --- corpus builder ---------------------------------------------------------
def test_build_from_corpus_sanitizes(tmp_path):
    (tmp_path / "log_x.json").write_text(
        '{"error_code": "PAY-1001", "email": "a@b.com", "pan": "4111 1111 1111 1111"}',
        encoding="utf-8",
    )
    retriever = build_bm25_from_corpus(str(tmp_path), chunk_size=500, overlap=50)
    assert retriever.count() == 1
    # PII must not be searchable — the index inherits load_corpus's sanitization.
    assert retriever.retrieve("a@b.com", top_k=5) == []
    assert retriever.retrieve("4111", top_k=5) == []
    # ...while the useful lexical content is still indexed.
    assert retriever.retrieve("PAY-1001", top_k=5)
