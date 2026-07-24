"""Tests for corpus loading, chunking, and indexing."""

from __future__ import annotations

import pytest

from payment_assistant.models import Document
from payment_assistant.rag.ingestion import (
    _infer_doc_type,
    _infer_title,
    chunk_document,
    ingest,
    load_corpus,
)
from tests.conftest import FakeEmbeddings, FakeVectorStore


def test_infer_doc_type_from_prefix():
    assert _infer_doc_type("runbook_x.md") == "runbook"
    assert _infer_doc_type("errorcodes_payment.md") == "error_codes"
    assert _infer_doc_type("mystery.md") == "document"  # fallback


def test_infer_title_prefers_markdown_heading():
    assert _infer_title("# Payments API\nbody", "fallback") == "Payments API"
    assert _infer_title("plain first line\nmore", "fallback") == "plain first line"
    assert _infer_title("", "fallback") == "fallback"


def test_load_corpus_sanitizes_documents(tmp_path):
    (tmp_path / "log_x.json").write_text(
        '{"email": "a@b.com", "pan": "4111 1111 1111 1111"}', encoding="utf-8"
    )
    (tmp_path / "notes.png").write_bytes(b"\x89PNG")  # unsupported suffix ignored

    docs = load_corpus(str(tmp_path))
    assert len(docs) == 1  # png skipped
    doc = docs[0]
    assert "a@b.com" not in doc.text and "4111" not in doc.text
    assert "[EMAIL]" in doc.text and "[CARD]" in doc.text
    assert doc.doc_type == "log_sample"


def test_same_stem_different_extension_gets_unique_ids(tmp_path):
    """report.json / report.xml must not collapse into one id (they would overwrite
    each other's chunks in the vector store)."""
    (tmp_path / "log_a.json").write_text('{"status": "failed"}', encoding="utf-8")
    (tmp_path / "log_a.xml").write_text("<log><status>failed</status></log>", encoding="utf-8")

    docs = load_corpus(str(tmp_path))
    ids = [d.id for d in docs]
    assert len(ids) == len(set(ids)) == 2
    assert "log_a" in ids and "log_a_xml" in ids


def test_load_corpus_missing_dir_raises():
    with pytest.raises(FileNotFoundError):
        load_corpus("this/does/not/exist")


def test_chunk_document_single_window_for_small_doc():
    doc = Document(id="d", title="T", doc_type="faq", text="short body", source_path="d.md")
    chunks = chunk_document(doc, chunk_size=1000, overlap=100)
    assert len(chunks) == 1
    assert chunks[0].id == "d::0"
    assert chunks[0].document_id == "d"


def test_chunk_document_multiple_windows():
    paras = "\n\n".join(f"paragraph number {i} " * 5 for i in range(10))
    doc = Document(id="big", title="T", doc_type="guide", text=paras, source_path="big.md")
    chunks = chunk_document(doc, chunk_size=120, overlap=20)
    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunk_document_hard_splits_oversized_paragraph():
    doc = Document(id="huge", title="T", doc_type="guide", text="x" * 500, source_path="h.md")
    chunks = chunk_document(doc, chunk_size=100, overlap=20)
    assert len(chunks) > 1  # single long paragraph gets hard-split


def test_chunk_document_empty_text():
    doc = Document(id="e", title="T", doc_type="faq", text="   ", source_path="e.md")
    assert chunk_document(doc, 100, 10) == []


def test_ingest_indexes_and_resets(tmp_path):
    (tmp_path / "faq_a.md").write_text("# A\n\nfirst\n\nsecond", encoding="utf-8")
    (tmp_path / "guide_b.md").write_text("# B\n\nbody", encoding="utf-8")
    store = FakeVectorStore()
    embedder = FakeEmbeddings()

    count = ingest(str(tmp_path), embedder, store, chunk_size=1000, overlap=100)
    assert count == store.count() == 2
    assert store.reset_called == 1
    assert embedder.doc_calls  # documents were embedded


def test_ingest_without_reset(tmp_path):
    (tmp_path / "faq_a.md").write_text("# A\n\nbody", encoding="utf-8")
    store = FakeVectorStore()
    ingest(str(tmp_path), FakeEmbeddings(), store, chunk_size=500, overlap=50, reset=False)
    assert store.reset_called == 0


def test_ingest_empty_corpus_returns_zero(tmp_path):
    (tmp_path / "readme.png").write_bytes(b"x")  # no supported docs
    store = FakeVectorStore()
    assert ingest(str(tmp_path), FakeEmbeddings(), store, chunk_size=500, overlap=50) == 0
