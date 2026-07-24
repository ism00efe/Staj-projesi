"""Tests for domain models."""

from __future__ import annotations

from payment_assistant.models import Answer, Chunk, Citation, Document, RetrievedChunk


def test_chunk_metadata_shape():
    chunk = Chunk(
        id="d::0", document_id="d", title="Title", doc_type="faq",
        text="body", chunk_index=3, source_path="d.md",
    )
    meta = chunk.metadata()
    assert meta == {
        "document_id": "d",
        "title": "Title",
        "doc_type": "faq",
        "chunk_index": 3,
        "source_path": "d.md",
    }


def test_document_defaults():
    doc = Document(id="d", title="T", doc_type="faq", text="x", source_path="d.md")
    assert doc.metadata == {}


def test_answer_composition():
    chunk = Chunk("d::0", "d", "T", "faq", "x", 0, "d.md")
    ans = Answer(
        text="hi [S1]",
        citations=[Citation("S1", "d", "T", "faq", "d.md", 0.9)],
        retrieved=[RetrievedChunk(chunk, 0.9)],
        redactions=["[EMAIL]×1"],
        trace_id="abc123",
    )
    assert ans.citations[0].document_id == "d"
    assert ans.retrieved[0].score == 0.9
    assert ans.redactions == ["[EMAIL]×1"]
    assert ans.trace_id == "abc123"


def test_answer_trace_id_defaults_to_empty_string():
    ans = Answer(text="hi", citations=[], retrieved=[])
    assert ans.trace_id == ""
