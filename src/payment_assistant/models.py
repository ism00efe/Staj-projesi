"""Domain models shared across layers.

Plain dataclasses with no external dependencies. These are the vocabulary the whole
system speaks (documents, chunks, retrieval results, citations, answers), which keeps
the pipeline decoupled from any specific vector store, embedder, or LLM SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Document:
    """A source document in the knowledge base (synthetic or, later, real)."""

    id: str
    title: str
    doc_type: str
    text: str
    source_path: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    """A retrievable slice of a :class:`Document`."""

    id: str
    document_id: str
    title: str
    doc_type: str
    text: str
    chunk_index: int
    source_path: str

    def metadata(self) -> dict[str, str | int]:
        """Flat metadata dict stored alongside the vector (used for citations)."""

        return {
            "document_id": self.document_id,
            "title": self.title,
            "doc_type": self.doc_type,
            "chunk_index": self.chunk_index,
            "source_path": self.source_path,
        }


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk returned by similarity search, with its relevance score."""

    chunk: Chunk
    score: float


@dataclass(frozen=True)
class Citation:
    """A source referenced by the generated answer."""

    tag: str  # e.g. "S1"
    document_id: str
    title: str
    doc_type: str
    source_path: str
    score: float


@dataclass(frozen=True)
class Answer:
    """The assistant's response to a question / log."""

    text: str
    citations: list[Citation]
    retrieved: list[RetrievedChunk]
    redactions: list[str] = field(default_factory=list)
