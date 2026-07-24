"""Ingest the corpus into the vector store (load -> sanitize -> chunk -> embed -> index).

Usage:  python scripts/ingest.py
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

from payment_assistant.config import configure_logging, get_settings
from payment_assistant.rag.embeddings import SentenceTransformerEmbeddings
from payment_assistant.rag.ingestion import ingest
from payment_assistant.rag.vectorstore import ChromaVectorStore


def main() -> None:
    configure_logging()
    settings = get_settings()

    embedder = SentenceTransformerEmbeddings(settings.embedding_model)
    store = ChromaVectorStore(settings.chroma_persist_dir, settings.chroma_collection)

    count = ingest(
        settings.corpus_dir,
        embedder,
        store,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
        reset=True,
    )
    print(f"Indexed {count} chunks. Vector store now holds {store.count()} vectors.")
    print("Next: python scripts/run_app.py   (or: python -m payment_assistant.ui.app)")


if __name__ == "__main__":
    main()
