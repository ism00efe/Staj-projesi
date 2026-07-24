"""Tests for the sentence-transformers embedding wrapper (E5 prefixing).

A fake SentenceTransformer is injected so no real model is downloaded/loaded.
"""

from __future__ import annotations

import numpy as np
import pytest
import sentence_transformers

from payment_assistant.rag.embeddings import SentenceTransformerEmbeddings


class FakeST:
    last_texts: list[str] = []

    def __init__(self, model_name, device=None):
        self.model_name = model_name

    def encode(self, texts, normalize_embeddings=False, convert_to_numpy=True,
               show_progress_bar=False):
        FakeST.last_texts = list(texts)
        return np.array([[1.0, 2.0, 3.0] for _ in texts])


@pytest.fixture(autouse=True)
def _patch_st(monkeypatch):
    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", FakeST)
    FakeST.last_texts = []


def test_e5_model_adds_passage_and_query_prefixes():
    emb = SentenceTransformerEmbeddings("intfloat/multilingual-e5-small")

    emb.embed_documents(["hello"])
    assert FakeST.last_texts == ["passage: hello"]

    emb.embed_query("world")
    assert FakeST.last_texts == ["query: world"]


def test_non_e5_model_no_prefixes():
    emb = SentenceTransformerEmbeddings("sentence-transformers/all-MiniLM-L6-v2")
    emb.embed_documents(["hello"])
    assert FakeST.last_texts == ["hello"]
    emb.embed_query("world")
    assert FakeST.last_texts == ["world"]


def test_returns_plain_lists():
    emb = SentenceTransformerEmbeddings("intfloat/multilingual-e5-small")
    docs = emb.embed_documents(["a", "b"])
    assert isinstance(docs, list) and isinstance(docs[0], list)
    assert emb.embed_query("q") == [1.0, 2.0, 3.0]
