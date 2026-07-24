"""Tests for the Chroma vector store implementation (real Chroma, temp dir)."""

from __future__ import annotations

from payment_assistant.rag.vectorstore import ChromaVectorStore
from tests.conftest import make_chunk


def _store(tmp_path) -> ChromaVectorStore:
    return ChromaVectorStore(str(tmp_path / "chroma"), "test_kb")


def test_add_query_count(tmp_path):
    store = _store(tmp_path)
    chunks = [
        make_chunk("errorcodes_payment", 0, text="insufficient funds PAY-1001"),
        make_chunk("faq_general", 0, text="idempotency key usage"),
    ]
    embeddings = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    store.add(chunks, embeddings)

    assert store.count() == 2
    results = store.query([1.0, 0.0, 0.0], top_k=2)
    assert results[0].chunk.document_id == "errorcodes_payment"  # nearest to query
    assert results[0].chunk.doc_type == "faq"  # metadata round-trips
    assert results[0].score >= results[1].score  # sorted by similarity


def test_add_empty_is_noop(tmp_path):
    store = _store(tmp_path)
    store.add([], [])
    assert store.count() == 0


def test_reset_clears_collection(tmp_path):
    store = _store(tmp_path)
    store.add([make_chunk("a")], [[1.0, 0.0, 0.0]])
    assert store.count() == 1
    store.reset()
    assert store.count() == 0


def test_persistence_across_instances(tmp_path):
    store = _store(tmp_path)
    store.add([make_chunk("a", text="hello")], [[1.0, 0.0, 0.0]])
    # A new client pointed at the same dir/collection should see the data.
    reopened = ChromaVectorStore(str(tmp_path / "chroma"), "test_kb")
    assert reopened.count() == 1
