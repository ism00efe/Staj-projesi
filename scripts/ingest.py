"""Ingest the corpus into the vector store (load -> sanitize -> chunk -> embed -> index).

Usage:  python scripts/ingest.py
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

from payment_assistant.config import configure_logging, get_settings
from payment_assistant.embeddings import SentenceTransformerEmbeddings
from payment_assistant.ingestion import ingest
from payment_assistant.vectorstore import ChromaVectorStore


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
    print("Next: python -m payment_assistant.app   (or: python scripts/run_app.py)")


if __name__ == "__main__":
    main()
