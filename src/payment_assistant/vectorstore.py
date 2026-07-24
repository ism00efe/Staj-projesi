"""Vector store abstraction + ChromaDB implementation.

The pipeline talks to the ``VectorStore`` protocol only, so Chroma can later be swapped
for FAISS/Qdrant without touching ingestion or retrieval. Chunk metadata is stored
alongside each vector so retrieval can produce citations.
"""

from __future__ import annotations

import logging
from typing import Protocol

from .models import Chunk, RetrievedChunk

logger = logging.getLogger(__name__)


class VectorStore(Protocol):
    """Minimal interface the RAG pipeline needs from a vector database."""

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...

    def query(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]: ...

    def count(self) -> int: ...

    def reset(self) -> None: ...


class ChromaVectorStore:
    """Persistent local Chroma collection using cosine distance."""

    def __init__(self, persist_dir: str, collection_name: str) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Chroma ready (dir=%s, collection=%s, count=%d)",
            persist_dir,
            collection_name,
            self.count(),
        )

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        self._collection.add(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[dict(c.metadata()) for c in chunks],
        )

    def query(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]

        retrieved: list[RetrievedChunk] = []
        for cid, text, meta, dist in zip(ids, docs, metas, dists):
            chunk = Chunk(
                id=cid,
                document_id=str(meta.get("document_id", "")),
                title=str(meta.get("title", "")),
                doc_type=str(meta.get("doc_type", "")),
                text=text,
                chunk_index=int(meta.get("chunk_index", 0)),
                source_path=str(meta.get("source_path", "")),
            )
            # Chroma returns cosine distance in [0, 2]; convert to a similarity score.
            retrieved.append(RetrievedChunk(chunk=chunk, score=1.0 - float(dist)))
        return retrieved

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        """Drop and recreate the collection (used before a fresh ingest)."""

        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Collection '%s' reset.", self._collection_name)
