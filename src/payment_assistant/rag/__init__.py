"""RAG pipeline: sanitization-aware ingestion, embeddings, vector store, and the engine.

Re-exports the pieces the composition root wires together, so callers can do
``from payment_assistant.rag import RAGEngine`` without knowing the module split.
"""

from .embeddings import EmbeddingProvider, SentenceTransformerEmbeddings
from .engine import RAGEngine
from .ingestion import chunk_document, ingest, load_corpus
from .reranker import CrossEncoderReranker, Reranker
from .retriever import (
    DenseRetriever,
    HybridRetriever,
    Retriever,
    reciprocal_rank_fusion,
)
from .sparse_retriever import BM25Retriever, build_bm25_from_corpus
from .vectorstore import ChromaVectorStore, VectorStore

__all__ = [
    "EmbeddingProvider",
    "SentenceTransformerEmbeddings",
    "RAGEngine",
    "chunk_document",
    "ingest",
    "load_corpus",
    "ChromaVectorStore",
    "VectorStore",
    # retrieval layer
    "Retriever",
    "DenseRetriever",
    "HybridRetriever",
    "reciprocal_rank_fusion",
    "BM25Retriever",
    "build_bm25_from_corpus",
    "Reranker",
    "CrossEncoderReranker",
]
