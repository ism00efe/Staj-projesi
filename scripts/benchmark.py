"""Benchmark the full RAG pipeline across three quality tiers.

Usage:
  python scripts/benchmark.py                                  # all 3 tiers
  python scripts/benchmark.py --tier fast                       # one tier only
  python scripts/benchmark.py --tier full-quality --sample-size 10   # quick smoke test
  python scripts/benchmark.py --hardware-label "Colab T4, 16 GB" --output out.md

Tiers (rationale in DECISIONS.md D26):
  fast          dense-only retrieval + qwen2.5:0.5b-instruct
                (lowest latency/VRAM, runs on a CPU-only box)
  balanced      hybrid retrieval (dense + BM25, RRF-fused), no re-ranker
                + qwen2.5:7b-instruct
  full-quality  hybrid + cross-encoder re-rank + qwen2.5:7b-instruct
                (best retrieval quality measured in this repo -- see the Evaluation
                section of README.md -- but the reranker's ~2.2 GB plus a resident 7B
                Ollama model can exceed an 8 GB GPU's VRAM budget. An OOM on this tier
                is an expected hardware limit, reported as such below, not a bug.)

Requires:
  - A running Ollama server (`ollama serve`). Each tier's model is checked against
    `GET /api/tags` and pulled automatically (`ollama pull <model>`) if not already
    present -- see `_ensure_ollama_model_pulled`. No manual pull is required, though
    pre-pulling avoids a multi-GB download happening in the middle of a benchmark run.
  - The corpus generated and ingested:
      python scripts/generate_data.py && python scripts/ingest.py
  - Dev dependencies (numpy is already a core dependency):
      pip install -e ".[dev]"

Each tier is measured against the labeled `eval/dataset.jsonl` set:
  - retrieval quality: recall@1/3/5 and MRR, via eval/evaluate.py's own scoring
    functions (imported, not reimplemented, so both scripts always agree)
  - full pipeline: one AssistantService.ask() call per question, end-to-end
    (sanitize -> guard -> retrieve -> rerank -> generate -> cite), timed individually
    to report median / p95 latency
  - citation precision and groundedness, same definitions as
    `eval/evaluate.py --with-llm`
  - peak GPU memory used system-wide during the tier's run, sampled via `nvidia-smi`
    (falls back to "n/a" when no NVIDIA GPU is visible)

Writes a Markdown comparison table to `benchmark_results.md` (or --output). The table's
"Hardware" column is meant to be extended: `colab/colab_benchmark.ipynb` runs the same
script with `--tier full-quality --hardware-label "Colab T4, 16 GB"` and its output row
is added to the same table (see README.md's Benchmarks section).
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import _bootstrap  # noqa: F401  (adds src/ to sys.path)
import numpy as np
import requests

# eval/ has no __init__.py (it is a script directory, not a package) but Python 3's
# implicit namespace packages make `eval.evaluate` importable regardless, as long as the
# repo root -- not just src/ -- is on sys.path. _bootstrap only adds src/, so it is added
# here too, the same way eval/evaluate.py adds src/ itself when run standalone.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.evaluate import evaluate_retrieval, load_dataset  # noqa: E402
from payment_assistant.config import Settings, configure_logging, get_settings  # noqa: E402
from payment_assistant.llm import build_llm_provider  # noqa: E402
from payment_assistant.rag import (  # noqa: E402
    ChromaVectorStore,
    RAGEngine,
    SentenceTransformerEmbeddings,
)
from payment_assistant.service import AssistantService, build_retriever  # noqa: E402

logger = logging.getLogger(__name__)

# Every nvidia-smi call below can fail the same ways: the binary is missing (no NVIDIA
# GPU), it exits non-zero, it hangs, or its output doesn't parse as a number.
_NVIDIA_SMI_ERRORS = (
    FileNotFoundError,
    subprocess.CalledProcessError,
    subprocess.TimeoutExpired,
    ValueError,
    IndexError,
)


@dataclass(frozen=True)
class Tier:
    name: str
    hybrid: bool
    rerank: bool
    ollama_model: str
    description: str


TIERS: dict[str, Tier] = {
    "fast": Tier(
        "fast",
        hybrid=False,
        rerank=False,
        ollama_model="qwen2.5:0.5b-instruct",
        description="dense-only retrieval, smallest LLM -- lowest latency/VRAM",
    ),
    "balanced": Tier(
        "balanced",
        hybrid=True,
        rerank=False,
        ollama_model="qwen2.5:7b-instruct",
        description="hybrid dense+BM25 retrieval (RRF), no re-ranker",
    ),
    "full-quality": Tier(
        "full-quality",
        hybrid=True,
        rerank=True,
        ollama_model="qwen2.5:7b-instruct",
        description="hybrid + cross-encoder re-rank -- needs >8 GB VRAM",
    ),
}

_STATUS_LABELS = {"ok": "OK", "oom": "OOM (requires >8 GB VRAM)"}


@dataclass
class TierResult:
    tier: str
    hardware: str
    status: str  # "ok" | "oom"
    detail: str = ""
    n_questions: int = 0
    recall_at_5: float | None = None
    mrr: float | None = None
    citation_precision: float | None = None
    groundedness: float | None = None
    latency_p50: float | None = None
    latency_p95: float | None = None
    gpu_mem_used_mb: float | None = None
    by_category: dict = field(default_factory=dict)


def _gpu_memory_used_mb() -> float | None:
    """Total GPU memory in use, system-wide (across every process, every GPU).

    Shells out to `nvidia-smi` rather than reading `torch.cuda.memory_allocated()`:
    Ollama runs as its own OS process with its own CUDA context, so torch's in-process
    counters would only ever see this script's own (embedder/reranker) allocations --
    not the LLM's, which is most of what actually determines whether a tier fits an
    8 GB card. Returns None (never 0) when no NVIDIA GPU is visible, so callers can
    render "n/a" instead of a misleading zero.
    """

    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        values = [float(line) for line in proc.stdout.splitlines() if line.strip()]
        return max(values) if values else None
    except _NVIDIA_SMI_ERRORS:
        return None


def _detect_hardware_label() -> str:
    """Best-effort hardware name for the results table (overridable via --hardware-label)."""

    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        name, total = (part.strip() for part in proc.stdout.strip().splitlines()[0].split(","))
        total_gb = round(float(total.split()[0]) / 1024)
        return f"{name}, {total_gb} GB"
    except _NVIDIA_SMI_ERRORS:
        return "CPU (no GPU detected)"


def _ensure_ollama_model_pulled(settings: Settings) -> None:
    """Pull `settings.ollama_model` via the Ollama CLI if it isn't already present locally.

    Checked before every tier runs, not just once at startup, since different tiers can
    name different models (fast uses a small model, balanced/full-quality a larger one --
    and a future tier is free to name a third). Only applies when LLM_PROVIDER=ollama;
    other providers have no local model to pull. Lets a fresh machine (a new dev box, a
    Colab runtime) run any tier without a separate manual `ollama pull` per model.
    """

    if settings.llm_provider.strip().lower() != "ollama":
        return

    model = settings.ollama_model
    base_url = settings.ollama_base_url.rstrip("/")

    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=10)
        resp.raise_for_status()
        local_models = {entry["name"] for entry in resp.json().get("models", [])}
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {base_url} to check installed models. "
            "Is `ollama serve` running?"
        ) from exc

    if model in local_models:
        print(f"  (model '{model}' already pulled)")
        return

    print(f"  Model '{model}' not found locally -- pulling (this can take a while)...")
    try:
        subprocess.run(["ollama", "pull", model], check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "The `ollama` CLI is not on PATH -- install it from https://ollama.com "
            f"or pull '{model}' manually."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"`ollama pull {model}` failed (exit code {exc.returncode}).") from exc


def _looks_like_oom(exc: Exception) -> bool:
    text = str(exc).lower()
    return "out of memory" in text or ("cuda" in text and "memory" in text)


@contextmanager
def _env_file_guard():
    """Snapshot `.env` (if present) and restore it byte-for-byte afterward.

    Every tier below is built via `Settings.model_copy(update=...)` entirely in-process
    -- nothing in this script writes `.env`. This guard is kept anyway as explicit,
    cheap insurance: it guarantees the repo's own `.env` can never be left mutated by a
    benchmark run (including one that crashes mid-tier), even if a future tier needs to
    shell out to a subprocess that reads config from `.env` rather than accepting
    overrides directly.
    """

    env_path = _ROOT / ".env"
    original = env_path.read_bytes() if env_path.exists() else None
    try:
        yield
    finally:
        if original is not None:
            env_path.write_bytes(original)
        elif env_path.exists():
            env_path.unlink()


def _run_llm_pipeline(
    service: AssistantService, dataset: list[dict], sample_size: int | None
) -> tuple[list[float], list[float], list[float], float | None]:
    """Time one AssistantService.ask() call per question; score citations same as eval/evaluate.py.

    Returns (latencies_seconds, citation_precisions, groundedness_scores, peak_gpu_mem_mb).
    """

    items = dataset if sample_size is None else dataset[:sample_size]
    latencies: list[float] = []
    precisions: list[float] = []
    groundedness: list[float] = []
    mem_samples: list[float] = []

    for i, item in enumerate(items, start=1):
        expected = set(item["expected_sources"])
        start = time.perf_counter()
        answer = service.ask(item["question"])
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

        mem = _gpu_memory_used_mb()
        if mem is not None:
            mem_samples.append(mem)

        cited = {c.document_id for c in answer.citations}
        retrieved_ids = {r.chunk.document_id for r in answer.retrieved}
        if cited:
            precisions.append(len(cited & expected) / len(cited))
            groundedness.append(len(cited & retrieved_ids) / len(cited))
        else:
            precisions.append(0.0)
            groundedness.append(1.0)  # nothing cited -> nothing fabricated

        print(f"  [{i}/{len(items)}] {elapsed:5.2f}s  {item['question'][:60]}")

    peak_mem = max(mem_samples) if mem_samples else None
    return latencies, precisions, groundedness, peak_mem


def run_tier(
    tier: Tier,
    base_settings: Settings,
    embedder: SentenceTransformerEmbeddings,
    store: ChromaVectorStore,
    dataset: list[dict],
    hardware_label: str,
    sample_size: int | None,
) -> TierResult:
    """Run one tier end-to-end. An OOM is caught and reported as a row, not raised."""

    settings = base_settings.model_copy(
        update={
            "hybrid_enabled": tier.hybrid,
            "rerank_enabled": tier.rerank,
            "ollama_model": tier.ollama_model,
            # Each tier constructs its own Settings in this one process; without this,
            # the second tier's build_service-equivalent wiring would try to start a
            # second Prometheus HTTP server on the same port and crash.
            "metrics_enabled": False,
        }
    )

    try:
        _ensure_ollama_model_pulled(settings)

        retriever = build_retriever(
            settings, embedder, store, hybrid=tier.hybrid, rerank=tier.rerank
        )
        retrieval_metrics = evaluate_retrieval(retriever, dataset, max_k=5)

        llm = build_llm_provider(settings)
        engine = RAGEngine(
            embedder,
            store,
            llm,
            top_k=settings.top_k,
            retriever=retriever,
            input_guard_enabled=settings.input_guard_enabled,
        )
        service = AssistantService(engine, settings)

        latencies, precisions, groundedness, peak_mem = _run_llm_pipeline(
            service, dataset, sample_size
        )

        return TierResult(
            tier=tier.name,
            hardware=hardware_label,
            status="ok",
            n_questions=len(latencies),
            recall_at_5=retrieval_metrics["recall"][5],
            mrr=retrieval_metrics["mrr"],
            citation_precision=sum(precisions) / len(precisions),
            groundedness=sum(groundedness) / len(groundedness),
            latency_p50=float(np.percentile(latencies, 50)),
            latency_p95=float(np.percentile(latencies, 95)),
            gpu_mem_used_mb=peak_mem,
            by_category={
                cat: round(v["mrr"], 3) for cat, v in retrieval_metrics["by_category"].items()
            },
        )
    except RuntimeError as exc:
        if _looks_like_oom(exc):
            logger.warning("Tier '%s' hit an out-of-memory condition: %s", tier.name, exc)
            return TierResult(
                tier=tier.name, hardware=hardware_label, status="oom", detail=str(exc)
            )
        raise


def _fmt(value: float | None, spec: str = "{:.3f}") -> str:
    return spec.format(value) if value is not None else "n/a"


def format_table(results: list[TierResult]) -> str:
    header = (
        "| Hardware | Tier | Recall@5 | MRR | Citation Precision | Groundedness | "
        "Latency p50 (s) | Latency p95 (s) | Peak GPU Mem (MB) | Status |"
    )
    separator = "|---|---|---|---|---|---|---|---|---|---|"
    rows = [header, separator]
    for r in results:
        rows.append(
            f"| {r.hardware} | {r.tier} | {_fmt(r.recall_at_5)} | {_fmt(r.mrr)} | "
            f"{_fmt(r.citation_precision)} | {_fmt(r.groundedness)} | "
            f"{_fmt(r.latency_p50, '{:.2f}')} | {_fmt(r.latency_p95, '{:.2f}')} | "
            f"{_fmt(r.gpu_mem_used_mb, '{:.0f}')} | {_STATUS_LABELS.get(r.status, r.status)} |"
        )
    return "\n".join(rows)


def write_results(results: list[TierResult], output_path: Path, dataset_size: int) -> None:
    lines = [
        "# Benchmark Results",
        "",
        f"Generated by `python scripts/benchmark.py`. {dataset_size} eval questions "
        "(`eval/dataset.jsonl`); retrieval metrics reuse `eval/evaluate.py`'s own scoring "
        "so both scripts always agree.",
        "",
        format_table(results),
    ]

    oom_rows = [r for r in results if r.status == "oom"]
    if oom_rows:
        lines += ["", "**OOM detail:**"]
        lines += [f"- `{r.tier}` on {r.hardware}: {r.detail}" for r in oom_rows]

    ok_rows = [r for r in results if r.status == "ok" and r.by_category]
    if ok_rows:
        categories = sorted({c for r in ok_rows for c in r.by_category})
        header = "| Tier | " + " | ".join(categories) + " |"
        lines += ["", "**MRR by question category:**", "", header]
        lines.append("|---|" + "---|" * len(categories))
        for r in ok_rows:
            cells = " | ".join(_fmt(r.by_category.get(c)) for c in categories)
            lines.append(f"| {r.tier} | {cells} |")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark the RAG pipeline across quality tiers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tier",
        nargs="+",
        choices=[*TIERS, "all"],
        default=["all"],
        help="One or more tiers to run, e.g. --tier fast balanced (default: all).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Limit to the first N eval questions instead of the full set (quick smoke test).",
    )
    parser.add_argument(
        "--hardware-label",
        default=None,
        help='Override the auto-detected hardware label, e.g. "Colab T4, 16 GB".',
    )
    parser.add_argument(
        "--output", default="benchmark_results.md", help="Output Markdown file path."
    )
    args = parser.parse_args()

    configure_logging()
    base_settings = get_settings()
    dataset = load_dataset()

    embedder = SentenceTransformerEmbeddings(
        base_settings.embedding_model, device=base_settings.embedding_device
    )
    store = ChromaVectorStore(base_settings.chroma_persist_dir, base_settings.chroma_collection)
    if store.count() == 0:
        raise SystemExit("Vector store is empty. Run `python scripts/ingest.py` first.")

    hardware_label = args.hardware_label or _detect_hardware_label()
    selected = list(TIERS) if "all" in args.tier else args.tier

    print(f"Hardware: {hardware_label}")
    print(f"Benchmarking {len(selected)} tier(s) against {len(dataset)} questions "
          f"({store.count()} indexed chunks).")

    results: list[TierResult] = []
    with _env_file_guard():
        for name in selected:
            tier = TIERS[name]
            print(f"\n--- {name} ({tier.description}) ---")
            results.append(
                run_tier(
                    tier,
                    base_settings,
                    embedder,
                    store,
                    dataset,
                    hardware_label,
                    args.sample_size,
                )
            )

    output_path = Path(args.output)
    write_results(results, output_path, len(dataset))

    print("\n" + format_table(results))
    print(f"\nWrote {output_path}")


if __name__ == "__main__":
    main()
