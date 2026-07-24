"""Shared pytest fixtures and lightweight fakes.

The pipeline is programmed against small interfaces (EmbeddingProvider, VectorStore,
LLMProvider, Retriever, Reranker), so these in-memory fakes let us test the RAG engine,
retrieval chain, ingestion, and the application service deterministically — without
loading models, Chroma, or an LLM.
"""

from __future__ import annotations

import pytest

from payment_assistant.models import Chunk, RetrievedChunk


class FakeEmbeddings:
    """Deterministic stand-in for an embedding provider.

    Returns a tiny fixed-dimension vector; records calls so tests can assert prefixes
    or query text were passed through.
    """

    def __init__(self) -> None:
        self.doc_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.doc_calls.append(list(texts))
        return [[float(len(t)), 1.0, 0.0] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return [float(len(text)), 1.0, 0.0]


class FakeVectorStore:
    """In-memory vector store honoring the VectorStore protocol.

    Ignores actual vector math: ``query`` returns the first ``top_k`` added chunks, which
    is enough to exercise retrieval, prompting, and citation wiring.
    """

    def __init__(self, chunks: list[Chunk] | None = None) -> None:
        self._chunks: list[Chunk] = list(chunks or [])
        self.reset_called = 0

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        self._chunks.extend(chunks)

    def query(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(chunk=c, score=1.0 - 0.1 * i)
            for i, c in enumerate(self._chunks[:top_k])
        ]

    def count(self) -> int:
        return len(self._chunks)

    def reset(self) -> None:
        self.reset_called += 1
        self._chunks = []


class FakeLLM:
    """LLM provider stub that returns a preset answer and records the last prompt."""

    def __init__(self, response: str = "Yanıt [S1].") -> None:
        self.response = response
        self.last_system: str | None = None
        self.last_user: str | None = None

    @property
    def name(self) -> str:
        return "fake"

    def generate(self, system: str, user: str) -> str:
        self.last_system = system
        self.last_user = user
        return self.response


class FakeRetriever:
    """Returns a preset ranking, recording the query and depth it was asked for."""

    def __init__(self, chunks: list[Chunk] | None = None) -> None:
        self._chunks = list(chunks or [])
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        self.calls.append((query, top_k))
        return [
            RetrievedChunk(chunk=c, score=1.0 - 0.1 * i)
            for i, c in enumerate(self._chunks[:top_k])
        ]


class FakeReranker:
    """Re-orders candidates by an explicit chunk-id preference list."""

    def __init__(self, preferred_order: list[str] | None = None) -> None:
        self.preferred_order = list(preferred_order or [])
        self.calls: list[tuple[str, int, int]] = []

    def rerank(
        self, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        self.calls.append((query, len(candidates), top_k))

        def rank_of(item: RetrievedChunk) -> int:
            cid = item.chunk.id
            return self.preferred_order.index(cid) if cid in self.preferred_order else 10**6

        ordered = sorted(candidates, key=rank_of)
        return ordered[:top_k]


def make_chunk(doc_id: str, index: int = 0, *, text: str = "content", title: str = "T",
               doc_type: str = "faq") -> Chunk:
    return Chunk(
        id=f"{doc_id}::{index}",
        document_id=doc_id,
        title=title,
        doc_type=doc_type,
        text=text,
        chunk_index=index,
        source_path=f"{doc_id}.md",
    )


@pytest.fixture
def fake_embeddings() -> FakeEmbeddings:
    return FakeEmbeddings()


@pytest.fixture
def fake_store() -> FakeVectorStore:
    return FakeVectorStore()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()
