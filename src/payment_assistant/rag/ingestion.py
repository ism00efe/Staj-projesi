"""Corpus ingestion: load -> sanitize -> chunk -> embed -> index.

This is the offline pipeline that populates the vector store. It is intentionally
agnostic about whether the corpus is synthetic or real: it only reads files from a
directory. Swapping in real enterprise documents means pointing ``CORPUS_DIR`` elsewhere.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import Chunk, Document
from ..sanitization import sanitize
from .embeddings import EmbeddingProvider
from .vectorstore import VectorStore

logger = logging.getLogger(__name__)

# Filename prefix -> document type. Keeps ingestion trivial and metadata clean (A3).
_PREFIX_TO_TYPE = {
    "api_": "api_doc",
    "runbook_": "runbook",
    "guide_": "troubleshooting_guide",
    "faq_": "faq",
    "errorcodes_": "error_codes",
    "log_": "log_sample",
    "trace_": "stack_trace",
    "concept_": "concept",
}

_TEXT_SUFFIXES = {".md", ".txt", ".json", ".xml", ".log"}


def _infer_doc_type(filename: str) -> str:
    for prefix, doc_type in _PREFIX_TO_TYPE.items():
        if filename.startswith(prefix):
            return doc_type
    return "document"


def _infer_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        if stripped:
            return stripped[:80]
    return fallback


def _unique_id(path: Path, seen: set[str]) -> str:
    """Derive a stable, collision-free document id from a file path.

    The id is the filename stem, which keeps ids readable and stable. Two files can share
    a stem (``report.pdf`` / ``report.docx``, or our ``log_err_x.json`` / ``.xml``), so a
    collision falls back to appending the extension, then a counter. Without this, both
    documents would produce identical chunk ids and silently overwrite each other in the
    vector store. Iteration order is sorted, so ids are deterministic across runs.
    """

    doc_id = path.stem
    if doc_id in seen:
        doc_id = f"{path.stem}_{path.suffix.lstrip('.').lower()}"
        counter = 2
        base = doc_id
        while doc_id in seen:  # pragma: no cover - needs a stem *and* stem+ext collision
            doc_id = f"{base}_{counter}"
            counter += 1
    seen.add(doc_id)
    return doc_id


def load_corpus(corpus_dir: str) -> list[Document]:
    """Read every supported file under ``corpus_dir`` into a :class:`Document`.

    Documents are sanitized here, once, before chunking — guaranteeing no sensitive
    value can reach the chunker, embedder, or vector store.
    """

    root = Path(corpus_dir)
    if not root.exists():
        raise FileNotFoundError(
            f"Corpus directory '{corpus_dir}' not found. "
            "Run `python scripts/generate_data.py` first."
        )

    documents: list[Document] = []
    seen_ids: set[str] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        clean = sanitize(raw)  # SECURITY: sanitize before anything downstream
        documents.append(
            Document(
                id=_unique_id(path, seen_ids),
                title=_infer_title(clean, path.stem),
                doc_type=_infer_doc_type(path.name),
                text=clean,
                source_path=str(path.relative_to(root)),
            )
        )
    logger.info("Loaded %d documents from %s", len(documents), corpus_dir)
    return documents


def chunk_document(doc: Document, chunk_size: int, overlap: int) -> list[Chunk]:
    """Split a document into overlapping, paragraph-aware character windows."""

    text = doc.text.strip()
    if not text:
        return []

    # Try to break on paragraph boundaries; fall back to hard windows for long blocks.
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    windows: list[str] = []
    buffer = ""
    for para in paragraphs:
        if len(buffer) + len(para) + 2 <= chunk_size:
            buffer = f"{buffer}\n\n{para}" if buffer else para
        else:
            if buffer:
                windows.append(buffer)
            if len(para) <= chunk_size:
                buffer = para
            else:
                # Paragraph longer than a window: hard-split it with overlap.
                start = 0
                while start < len(para):
                    windows.append(para[start : start + chunk_size])
                    start += max(1, chunk_size - overlap)
                buffer = ""
    if buffer:
        windows.append(buffer)

    return [
        Chunk(
            id=f"{doc.id}::{i}",
            document_id=doc.id,
            title=doc.title,
            doc_type=doc.doc_type,
            text=window,
            chunk_index=i,
            source_path=doc.source_path,
        )
        for i, window in enumerate(windows)
    ]


def ingest(
    corpus_dir: str,
    embedder: EmbeddingProvider,
    store: VectorStore,
    *,
    chunk_size: int,
    overlap: int,
    reset: bool = True,
) -> int:
    """Run the full ingestion pipeline. Returns the number of chunks indexed."""

    if reset:
        store.reset()

    documents = load_corpus(corpus_dir)
    chunks: list[Chunk] = []
    for doc in documents:
        chunks.extend(chunk_document(doc, chunk_size, overlap))

    if not chunks:
        logger.warning("No chunks produced from corpus '%s'.", corpus_dir)
        return 0

    logger.info("Embedding %d chunks...", len(chunks))
    embeddings = embedder.embed_documents([c.text for c in chunks])
    store.add(chunks, embeddings)
    logger.info("Indexed %d chunks from %d documents.", len(chunks), len(documents))
    return len(chunks)
