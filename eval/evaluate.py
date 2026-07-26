"""Evaluate and compare retrieval strategies.

Retrieval metrics (fast, no LLM):
  - recall@k : fraction of questions where >=1 expected source is in the top-k.
  - MRR      : mean reciprocal rank of the first relevant source.

Strategies:
  dense          : bi-encoder (multilingual-e5) + Chroma            [baseline]
  hybrid         : dense + BM25 sparse, fused with RRF
  hybrid-rerank  : hybrid, then a multilingual cross-encoder re-ranks the top candidates

Citation metrics (with --with-llm, requires a running provider):
  - citation precision : cited sources that are among the question's expected sources.
  - groundedness       : cited sources that were actually retrieved (never fabricated).

Usage:
  python eval/evaluate.py                        # compare all strategies
  python eval/evaluate.py --strategy dense       # a single strategy
  python eval/evaluate.py --strategy all --with-llm

Note: `hybrid-rerank` downloads the cross-encoder (~2.2 GB) on first run, then caches it.
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
from payment_assistant.rag.embeddings import SentenceTransformerEmbeddings  # noqa: E402
from payment_assistant.rag.vectorstore import ChromaVectorStore  # noqa: E402
from payment_assistant.service import build_retriever  # noqa: E402

_DATASET = Path(__file__).resolve().parent / "dataset.jsonl"
_K_VALUES = (1, 3, 5)

# strategy name -> (hybrid, rerank)
_STRATEGIES: dict[str, tuple[bool, bool]] = {
    "dense": (False, False),
    "hybrid": (True, False),
    "hybrid-rerank": (True, True),
}


def load_dataset() -> list[dict]:
    """Load the labeled evaluation questions (unknown keys are ignored)."""

    items = []
    for line in _DATASET.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def evaluate_retrieval(
    retriever, dataset: list[dict], max_k: int, *, verbose: bool = False
) -> dict:
    """Run one strategy over the dataset and return its metrics."""

    recall_hits = {k: 0 for k in _K_VALUES}
    reciprocal_ranks: list[float] = []
    per_category: dict[str, list[float]] = {}

    for item in dataset:
        expected = set(item["expected_sources"])
        retrieved = retriever.retrieve(item["question"], max_k)
        ranked_doc_ids = [r.chunk.document_id for r in retrieved]

        first_rank = next(
            (i for i, doc_id in enumerate(ranked_doc_ids, start=1) if doc_id in expected),
            None,
        )
        rr = 1.0 / first_rank if first_rank else 0.0
        reciprocal_ranks.append(rr)
        per_category.setdefault(item.get("category", "uncategorized"), []).append(rr)

        for k in _K_VALUES:
            if any(doc_id in expected for doc_id in ranked_doc_ids[:k]):
                recall_hits[k] += 1

        if verbose:
            status = f"rank={first_rank}" if first_rank else "MISS"
            print(f"  [{status:>7}] {item['question'][:64]}")

    n = len(dataset)
    return {
        "recall": {k: recall_hits[k] / n for k in _K_VALUES},
        "mrr": sum(reciprocal_ranks) / n,
        "by_category": {
            cat: {"mrr": sum(v) / len(v), "n": len(v)} for cat, v in sorted(per_category.items())
        },
    }


def print_comparison(results: dict[str, dict]) -> None:
    """Print the headline table comparing strategies."""

    print("\n" + "=" * 66)
    print("RETRIEVAL STRATEGY COMPARISON")
    print("=" * 66)
    header = (
        f"{'Strategy':<16}"
        + "".join(f"{'recall@' + str(k):>11}" for k in _K_VALUES)
        + f"{'MRR':>11}"
    )
    print(header)
    print("-" * 66)
    for name, m in results.items():
        row = f"{name:<16}" + "".join(f"{m['recall'][k]:>11.3f}" for k in _K_VALUES)
        print(row + f"{m['mrr']:>11.3f}")

    # Per-category MRR shows *where* each strategy wins.
    categories = sorted({c for m in results.values() for c in m["by_category"]})
    if categories:
        print("\nMRR by question category:")
        cat_header = f"{'Strategy':<16}" + "".join(f"{c:>16}" for c in categories)
        print(cat_header)
        print("-" * len(cat_header))
        for name, m in results.items():
            row = f"{name:<16}"
            for c in categories:
                row += f"{m['by_category'].get(c, {}).get('mrr', float('nan')):>16.3f}"
            print(row)
        counts = ", ".join(
            f"{c}={next(iter(results.values()))['by_category'][c]['n']}" for c in categories
        )
        print(f"({counts})")


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
    parser = argparse.ArgumentParser(description="Evaluate the RAG assistant's retrieval.")
    parser.add_argument(
        "--strategy",
        choices=[*_STRATEGIES, "all"],
        default="all",
        help="Retrieval strategy to evaluate (default: all, prints a comparison table).",
    )
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="Also run full answers and compute citation metrics (needs a provider).",
    )
    parser.add_argument("--verbose", action="store_true", help="Print per-question results.")
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    dataset = load_dataset()

    embedder = SentenceTransformerEmbeddings(
        settings.embedding_model, device=settings.embedding_device
    )
    store = ChromaVectorStore(settings.chroma_persist_dir, settings.chroma_collection)
    if store.count() == 0:
        raise SystemExit("Vector store is empty. Run `python scripts/ingest.py` first.")

    selected = list(_STRATEGIES) if args.strategy == "all" else [args.strategy]
    print(f"Evaluating {len(dataset)} questions against {store.count()} indexed chunks.")

    results: dict[str, dict] = {}
    for name in selected:
        hybrid, rerank = _STRATEGIES[name]
        retriever = build_retriever(settings, embedder, store, hybrid=hybrid, rerank=rerank)
        if args.verbose:
            print(f"\n--- {name} ---")
        results[name] = evaluate_retrieval(
            retriever, dataset, max_k=max(_K_VALUES), verbose=args.verbose
        )

    print_comparison(results)

    if args.with_llm:
        evaluate_citations(settings, dataset)


if __name__ == "__main__":
    main()
