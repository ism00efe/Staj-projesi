"""Local embedding provider.

Programmed against a small ``EmbeddingProvider`` protocol so the rest of the system does
not depend on sentence-transformers directly. The default implementation runs a local
multilingual model (E5), which is required because the knowledge base is English while
user questions are Turkish (cross-lingual retrieval).
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns text into vectors. Documents and queries are embedded separately because
    some models (E5) expect different prefixes for each."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbeddings:
    """Local embeddings via ``sentence-transformers``.

    E5 models are trained with ``"query: "`` / ``"passage: "`` prefixes; we add them
    automatically when the model name looks like an E5 model. Vectors are L2-normalized
    so a dot product equals cosine similarity.
    """

    def __init__(self, model_name: str, *, device: str | None = None) -> None:
        # Imported lazily so unit tests that don't need embeddings stay fast.
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model '%s'...", model_name)
        self._model = SentenceTransformer(model_name, device=device)
        self._model_name = model_name
        self._use_e5_prefixes = "e5" in model_name.lower()

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self._use_e5_prefixes:
            texts = [f"passage: {t}" for t in texts]
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        if self._use_e5_prefixes:
            text = f"query: {text}"
        return self._encode([text])[0]
