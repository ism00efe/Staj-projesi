"""RAG pipeline: sanitization-aware ingestion, embeddings, vector store, and the engine.

Re-exports the pieces the composition root wires together, so callers can do
``from payment_assistant.rag import RAGEngine`` without knowing the module split.
"""

from .embeddings import EmbeddingProvider, SentenceTransformerEmbeddings
from .engine import RAGEngine
from .ingestion import (
    EmptyContent,
    UnsupportedFileType,
    chunk_document,
    extract_text,
    ingest,
    ingest_single_document,
    load_corpus,
)
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
    "ingest_single_document",
    "extract_text",
    "UnsupportedFileType",
    "EmptyContent",
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
