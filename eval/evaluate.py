"""Evaluate retrieval (and optionally answer/citation) quality.

Retrieval metrics (fast, no LLM):
  - recall@k : fraction of questions where >=1 expected source is in the top-k.
  - MRR      : mean reciprocal rank of the first relevant source.

Citation metrics (with --with-llm, requires a running provider):
  - citation precision : cited sources that are among the question's expected sources.
  - groundedness       : cited sources that were actually retrieved (never fabricated).

Usage:
  python eval/evaluate.py
  python eval/evaluate.py --with-llm
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make src/ importable without an editable install.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from payment_assistant.config import configure_logging, get_settings  # noqa: E402
from payment_assistant.embeddings import SentenceTransformerEmbeddings  # noqa: E402
from payment_assistant.vectorstore import ChromaVectorStore  # noqa: E402

_DATASET = Path(__file__).resolve().parent / "dataset.jsonl"
_K_VALUES = (1, 3, 5)


def load_dataset() -> list[dict]:
    items = []
    for line in _DATASET.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def evaluate_retrieval(embedder, store, dataset: list[dict], max_k: int) -> None:
    recall_hits = {k: 0 for k in _K_VALUES}
    reciprocal_ranks = []

    print("\nPer-question retrieval:")
    for item in dataset:
        question = item["question"]
        expected = set(item["expected_sources"])
        vec = embedder.embed_query(question)
        retrieved = store.query(vec, max_k)
        ranked_doc_ids = [r.chunk.document_id for r in retrieved]

        # First rank where a retrieved doc is one of the expected sources.
        first_rank = next(
            (i for i, doc_id in enumerate(ranked_doc_ids, start=1) if doc_id in expected),
            None,
        )
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
        for k in _K_VALUES:
            if any(doc_id in expected for doc_id in ranked_doc_ids[:k]):
                recall_hits[k] += 1

        status = f"rank={first_rank}" if first_rank else "MISS"
        print(f"  [{status:>7}] {question[:60]}")

    n = len(dataset)
    print("\nRetrieval metrics:")
    for k in _K_VALUES:
        print(f"  recall@{k}: {recall_hits[k] / n:.2f} ({recall_hits[k]}/{n})")
    print(f"  MRR     : {sum(reciprocal_ranks) / n:.3f}")


def evaluate_citations(settings, dataset: list[dict]) -> None:
    from payment_assistant.service import build_service

    service = build_service(settings)
    precisions, groundedness = [], []

    print("\nPer-question answer/citation (LLM):")
    for item in dataset:
        expected = set(item["expected_sources"])
        answer = service.ask(item["question"])
        cited = {c.document_id for c in answer.citations}
        retrieved_ids = {r.chunk.document_id for r in answer.retrieved}
        if cited:
            precisions.append(len(cited & expected) / len(cited))
            groundedness.append(len(cited & retrieved_ids) / len(cited))
        else:
            precisions.append(0.0)
            groundedness.append(1.0)  # nothing cited -> nothing fabricated
        print(f"  cited={sorted(cited)} | expected={sorted(expected)}")

    n = len(dataset)
    print("\nCitation metrics:")
    print(f"  citation precision: {sum(precisions) / n:.2f}")
    print(f"  groundedness      : {sum(groundedness) / n:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the RAG assistant.")
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="Also run full answers and compute citation metrics (needs a provider).",
    )
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    dataset = load_dataset()

    embedder = SentenceTransformerEmbeddings(settings.embedding_model)
    store = ChromaVectorStore(settings.chroma_persist_dir, settings.chroma_collection)
    if store.count() == 0:
        raise SystemExit("Vector store is empty. Run `python scripts/ingest.py` first.")

    evaluate_retrieval(embedder, store, dataset, max_k=max(_K_VALUES))
    if args.with_llm:
        evaluate_citations(settings, dataset)


if __name__ == "__main__":
    main()
