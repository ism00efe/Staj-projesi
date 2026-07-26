"""Corpus ingestion: load -> sanitize -> chunk -> embed -> index.

Two entry points populate the vector store. ``ingest`` is the offline pipeline that reads
every file under a directory (the corpus loaded at startup); it is intentionally agnostic
about whether the corpus is synthetic or real, and swapping in real enterprise documents
means pointing ``CORPUS_DIR`` elsewhere. ``ingest_single_document`` is the online
counterpart the upload API calls: same sanitize -> chunk -> embed steps, but for one
already-in-memory document appended to an existing collection, never touching disk.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from uuid import uuid4

import filetype

from ..models import Chunk, Document
from ..sanitization import Redaction, sanitize, sanitize_text
from .embeddings import EmbeddingProvider
from .vectorstore import VectorStore

logger = logging.getLogger(__name__)


class UnsupportedFileType(ValueError):
    """Uploaded content doesn't match an accepted, content-verified file type."""


class EmptyContent(ValueError):
    """Uploaded content — or the text extracted from it — is empty."""


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
_UPLOAD_SUFFIXES = _TEXT_SUFFIXES | {".pdf"}


def _extract_pdf_text(content: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        # pypdf raises several distinct error types (PdfReadError, and plain ValueError /
        # KeyError from malformed structures) for a corrupt or non-standard PDF. All of
        # them mean the same thing to this caller: the bytes could not be read as a PDF.
        raise UnsupportedFileType(f"PDF içeriği okunamadı: {exc}") from exc
    return "\n\n".join(p for p in pages if p.strip())


def extract_text(filename: str, content: bytes) -> str:
    """Validate an uploaded file's content and extract its plain text.

    Validated by content, not the filename's extension. ``filetype.guess`` inspects magic
    bytes: a claimed ``.pdf`` must carry a real PDF signature, and content matching some
    *other* concrete binary signature (image, archive, executable, ...) is rejected
    outright, since none of the accepted formats are meant to be binary. Plain-text
    formats have no signature of their own — ``filetype.guess`` returns ``None`` for them
    by design — so those are instead validated by requiring a clean UTF-8 decode, which
    rejects binary garbage renamed with a text extension the same way.
    """

    suffix = Path(filename).suffix.lower()
    if suffix not in _UPLOAD_SUFFIXES:
        allowed = ", ".join(sorted(_UPLOAD_SUFFIXES))
        raise UnsupportedFileType(
            f"Desteklenmeyen dosya türü '{suffix or '(uzantısız)'}'. "
            f"Desteklenen türler: {allowed}"
        )
    if not content:
        raise EmptyContent("Yüklenen dosya boş.")

    kind = filetype.guess(content)
    if kind is not None:
        if suffix != ".pdf" or kind.extension != "pdf":
            raise UnsupportedFileType(
                f"Dosya içeriği '.{kind.extension}' olarak algılandı, bu '{suffix}' "
                "uzantısıyla eşleşmiyor ve kabul edilemez."
            )
        text = _extract_pdf_text(content)
    elif suffix == ".pdf":
        raise UnsupportedFileType("Dosya '.pdf' uzantılı ama bir PDF imzası taşımıyor.")
    else:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedFileType(
                "Dosya metne dönüştürülemedi (ikili veya bozuk içerik)."
            ) from exc

    if not text.strip():
        raise EmptyContent("Dosyadan çıkarılabilecek metin bulunamadı.")
    return text


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


def ingest_single_document(
    text: str,
    filename: str,
    embedder: EmbeddingProvider,
    store: VectorStore,
    *,
    chunk_size: int,
    overlap: int,
) -> tuple[int, list[Redaction]]:
    """Sanitize, chunk, embed, and add ONE document to an existing collection.

    The online counterpart to :func:`ingest`, used by the upload API. Never touches disk
    and never resets the store — ``store.add`` only appends, so the corpus loaded at
    startup is untouched. Both ``text`` and ``filename`` are sanitized: the filename ends
    up in stored metadata (title fallback, ``source_path``) and is operator-supplied, not
    developer-curated like a corpus path, so it gets the same guarantee as document text.

    The id gets a random suffix rather than reusing the filename stem the way corpus
    ingestion does: corpus ids only need to be unique within one directory listing, but an
    upload lands in a collection that may already hold any id, and colliding would either
    overwrite an existing document's chunks or fail outright depending on the store.
    """

    clean_filename, filename_redactions = sanitize_text(filename)
    clean_text, text_redactions = sanitize_text(text)
    redactions = filename_redactions + text_redactions

    doc = Document(
        id=f"upload_{uuid4().hex[:12]}",
        title=_infer_title(clean_text, Path(clean_filename).stem),
        doc_type=_infer_doc_type(clean_filename),
        text=clean_text,
        source_path=f"uploads/{clean_filename}",
    )
    chunks = chunk_document(doc, chunk_size, overlap)
    if not chunks:
        return 0, redactions

    embeddings = embedder.embed_documents([c.text for c in chunks])
    store.add(chunks, embeddings)
    logger.info("Indexed %d chunks from uploaded document '%s'.", len(chunks), doc.id)
    return len(chunks), redactions
