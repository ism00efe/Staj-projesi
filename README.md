# 💳 Payment Systems Knowledge & Log Analysis Assistant

A **RAG-based troubleshooting assistant for payment systems**. Ask a question or upload a
JSON/XML payment log; the assistant sanitizes the input, retrieves relevant material from
a local knowledge base, and generates **cited troubleshooting guidance** in Turkish.

> Internship MVP. The knowledge base ships with a **synthetic, bilingual** (Turkish +
> English) corpus modeled on real payment standards — ISO 8583, ISO 20022/SWIFT, EMV,
> card-scheme decline codes, and the Turkish payment ecosystem (BKM, Troy, FAST) — for a
> fictional bank ("Vera Bank"). The architecture lets you swap in real enterprise
> documents without changing the core system — you only point `CORPUS_DIR` somewhere
> else and re-ingest.

---

## Highlights

- **Local-first & privacy-preserving.** Embeddings and the vector DB run locally; the LLM
  defaults to a local Ollama model. Sensitive data is **masked before** it ever reaches
  embeddings, the vector store, or a prompt.
- **Provider-agnostic LLM.** Ollama (default), Anthropic, or OpenAI — chosen by an
  environment variable, behind one interface.
- **Cross-lingual retrieval.** Bilingual (Turkish + English) knowledge base — English for
  international standards and APIs, Turkish for internal runbooks and regulations — with
  Turkish questions and answers throughout, powered by a multilingual embedding model.
- **Cited answers.** Responses reference the exact source documents used.
- **Evaluable.** A small labeled set + metrics (recall@k, MRR, citation precision).

## How it works

```
              ┌──────────── ingestion (offline) ────────────┐
  corpus ──►  load ──► SANITIZE ──► chunk ──► embed ──► Chroma
              └──────────────────────────────────────────────┘

              ┌──────────────── query (online) ─────────────┐
  question ─┐                                                │
            ├─► SANITIZE ─► embed query ─► search ─► prompt ─┼─► LLM ─► cited answer
  log file ─┘   (+log summary)              (top-k)          │
              └──────────────────────────────────────────────┘
```

Sanitization runs on **both** paths. See [`DECISIONS.md`](DECISIONS.md) for why each
technology was chosen (with alternatives and tradeoffs), and [`CLAUDE.md`](CLAUDE.md) for
the engineering rules this project follows.

## Retrieval

Retrieval is a configurable three-stage chain:

```
query ─┬─► dense  (multilingual-e5 + Chroma) ─┐
       │                                       ├─► RRF fusion ─► top-N ─► cross-encoder ─► top_k
       └─► sparse (hand-rolled Okapi BM25) ───┘                          (optional)
```

- **Dense** captures meaning, so Turkish questions match English documents.
- **Sparse (BM25)** captures exact tokens — error codes (`RC-51`), endpoint paths, and
  English technical terms embedded in Turkish questions.
- **RRF** fuses by *rank*, not score, so no normalization between cosine and BM25 is needed.
- **Cross-encoder re-ranking** scores (query, document) jointly to separate near-identical
  documents. It **must be multilingual** here (`BAAI/bge-reranker-v2-m3`) — an English-only
  MS-MARCO model scores Turkish near-randomly and degrades ranking.

Every stage is togglable: `HYBRID_ENABLED`, `RERANK_ENABLED` (see the config table).

## Architecture

Clean, layered, and decoupled — the UI never contains business logic, and the RAG engine
depends only on small interfaces (embeddings / vector store / LLM), never on vendor SDKs.

The package is organized by architectural layer; `tests/` mirrors it.

```
src/payment_assistant/
  config.py           # typed settings (pydantic-settings + .env)
  models.py           # domain types: Document, Chunk, Citation, Answer, ...
  sanitization.py     # deterministic regex masking (security-critical, cross-cutting)
  service.py          # application service (composition root; UI calls only this)
  datagen.py          # synthetic corpus generator (v0)
  llm/                # LLMProvider protocol + ollama/anthropic/openai impls + factory
  observability/      # trace_id propagation, structured logging, Prometheus metrics
  security/           # prompt-injection guard (sanitization.py handles PII, above)
  rag/                # the RAG pipeline
    embeddings.py     #   EmbeddingProvider protocol + sentence-transformers impl
    vectorstore.py    #   VectorStore protocol + Chroma impl
    sparse_retriever.py #  hand-rolled Okapi BM25 (lexical retrieval)
    retriever.py      #   Retriever protocol, DenseRetriever adapter, RRF, HybridRetriever
    reranker.py       #   multilingual cross-encoder re-ranking (on by default)
    ingestion.py      #   load -> sanitize -> chunk -> embed -> index
    logs.py           #   JSON/XML log summarization
    prompts.py        #   versioned prompt templates
    engine.py         #   RAGEngine (retrieve -> prompt -> generate -> cite)
  ui/
    app.py            #   Gradio UI (presentation only)
scripts/              # generate_data.py, ingest.py, run_app.py
eval/                 # dataset.jsonl + evaluate.py
tests/                # mirrors the source tree; llm/ rag/ ui/ observability/ security/ + conftest fakes
```

## Prerequisites

- Python **3.11**
- [Ollama](https://ollama.com) running locally (for the default provider)
- ~5 GB disk for the default model, plus the embedding model (~0.5 GB) and the
  re-ranker (~2.2 GB), both downloaded once on first run
- Re-ranking is on by default and is CPU-usable, but ~6s/query on CPU-only torch. For
  the measured ~0.13s/query, install a CUDA build of torch matching your GPU driver
  (e.g. `pip install torch==2.13.0+cu130 --index-url
  https://download.pytorch.org/whl/cu130`) — or set `RERANK_ENABLED=false`.

## Quickstart

```bash
# 1) Environment
python -m venv .venv
.venv\Scripts\activate            # Windows (PowerShell/CMD)
# source .venv/bin/activate       # macOS/Linux
pip install -e .                    # or: pip install -e ".[dev]" for tests

# 2) Configure (optional — defaults work out of the box)
copy .env.example .env              # Windows   (cp on macOS/Linux)

# 3) Pull the local LLM (one-time, ~4.7 GB)
ollama pull qwen2.5:7b-instruct

# 4) Generate the synthetic corpus and index it
python scripts/generate_data.py
python scripts/ingest.py

# 5) Run the app  ->  http://127.0.0.1:7860
python scripts/run_app.py
```

Prefer a hosted LLM? Set `LLM_PROVIDER=anthropic` (or `openai`) and the matching API key
in `.env` — nothing else changes.

## Configuration

All settings live in `.env` (see [`.env.example`](.env.example)). Key ones:

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` \| `anthropic` \| `openai` |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Local model (strong Turkish, fits 8 GB VRAM) |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Local multilingual embeddings |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | Vector store location |
| `CORPUS_DIR` | `./data/corpus` | Knowledge-base documents |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `500` / `80` | Chunking (characters) |
| `TOP_K` | `4` | Retrieved chunks per query |
| `HYBRID_ENABLED` | `true` | Fuse BM25 sparse retrieval with dense (RRF) |
| `RERANK_ENABLED` | `true` | Cross-encoder re-ranking; needs CUDA torch to be fast |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | Must be multilingual (TR↔EN) |
| `RERANK_CANDIDATES` | `20` | Candidates passed to the re-ranker |
| `LOG_FORMAT` | `json` | `json` (structured) \| `text` (readable console) |
| `METRICS_ENABLED` | `false` | Expose Prometheus `/metrics` on `METRICS_PORT` |
| `METRICS_PORT` | `9090` | Port for the metrics HTTP server |
| `INPUT_GUARD_ENABLED` | `true` | Block prompt-injection patterns before the LLM |
| `MAX_UPLOAD_BYTES` | `2000000` | Reject uploaded log files above this size |

## Observability

Every request gets a `trace_id`, generated once in `RAGEngine.answer()` and propagated
to every layer (retriever, reranker, LLM provider) via a `contextvars.ContextVar` — no
function signature had to change to carry it. It's shown in the Gradio UI (`🔎 trace_id:
...`) and attached to every log line for that request, so a user-reported issue can be
traced end to end through the logs from one id.

**Structured logs.** `LOG_FORMAT=json` (default) emits one JSON object per line:

```json
{"timestamp": "...", "level": "INFO", "logger": "payment_assistant.rag.engine",
 "message": "step completed: retrieve", "trace_id": "a1b2c3d4e5f6",
 "step": "retrieve", "duration_ms": 42.1, "status": "ok", "chunk_count": 4}
```

Set `LOG_FORMAT=text` for a readable console format instead (still trace-id-tagged) —
useful while developing interactively.

**Metrics.** Collection (`rag_requests_total`, `rag_stage_duration_seconds` per stage,
`rag_sanitization_redactions_total` per PII category, `rag_retriever_strategy_total`)
always runs — it's cheap in-memory counters. `METRICS_ENABLED=true` additionally starts
a Prometheus HTTP server:

```bash
curl http://localhost:9090/metrics
```

Every label is a fixed, low-cardinality name (a stage, a redaction category, a strategy
name, a status word) — never request content, so the endpoint cannot leak query text or
PII by construction (verified in `tests/security/test_pii_leak_scan.py`).

For dashboards, an optional Prometheus + Grafana overlay is provided (kept out of the
core app on purpose):

```bash
# set METRICS_ENABLED=true first (env or docker-compose.yml)
docker compose -f docker-compose.yml -f docker-compose.observability.yml up
# Prometheus: http://localhost:9091   Grafana: http://localhost:3000 (admin/admin)
```

## Security

**Sanitization.** Deterministic, rule-based masking (never the LLM) runs before
embedding and before any LLM call. Masked categories: **credit cards** (Luhn-validated),
**Turkish IDs / TCKN** (checksum-validated), **IP addresses**, **emails**, **phone
numbers**, and **tokens/secrets** (JWT, Bearer, API keys). Checksum validation avoids
false positives on ordinary long numbers. Tests: [`tests/test_sanitization.py`](tests/test_sanitization.py).

**Prompt injection guard.** Before a (sanitized) query reaches retrieval or the LLM, a
deterministic regex pre-filter (`INPUT_GUARD_ENABLED=true` by default) checks for the
common override/jailbreak patterns — "ignore previous instructions", persona overrides
("you are now..."), injected `system:`/`assistant:` role lines, chat-template control
tokens (`<|im_start|>`, `[INST]`), and system-prompt exfiltration attempts. A match
returns a fixed refusal message and skips retrieval/generation entirely; the incident is
logged (category only, never the query text). Known limitation: patterns target English
jailbreak phrasing, documented in [`DECISIONS.md`](DECISIONS.md) (D18). Tests:
[`tests/security/test_guard.py`](tests/security/test_guard.py).

**Upload hardening.** Uploaded log files above `MAX_UPLOAD_BYTES` (default 2 MB) are
rejected before being read. XML content with a `DOCTYPE`/`ENTITY` declaration is
rejected before parsing (defends against entity-expansion / "billion laughs" DoS —
Python's `ElementTree` doesn't resolve *external* entities, but internal expansion can
still exhaust memory from a tiny payload). See D19 in `DECISIONS.md` for what's
deliberately *not* hardened here (path traversal, rate limiting) and why.

**PII leak-scan suite.** A dedicated test suite pushes fake-but-realistic PII (every
category above) through the real ingestion path, the real sparse index, a full
`RAGEngine.answer()` call, and captures every log line emitted along the way — then
asserts the raw values never appear anywhere: not in indexed chunks, not in the LLM
prompt, not in the LLM's response, not in a log line. This is the shape of test that
would have caught (and now guards against a repeat of) a real bug found during
development, where the BM25 sparse index was briefly built from unsanitized files.

```bash
pytest tests/security -v          # guard + PII leak-scan suite
pytest tests/security/test_pii_leak_scan.py -v   # just the leak-scan regression suite
```

## Testing

```bash
pip install -e ".[dev]"
pytest                              # run the suite
pytest --cov                        # with coverage summary
pytest --cov --cov-report=html      # detailed HTML report in htmlcov/
```

The suite is fast and offline (~230 tests, ~25s) — models, Chroma, the LLM, and the
Prometheus HTTP server are replaced by in-memory fakes/monkeypatches (`tests/conftest.py`),
except the vector-store tests which run real Chroma in a temp dir. Coverage is ~99% of
statements across the package (launch glue excluded).

## Evaluation

```bash
python eval/evaluate.py                       # compare all retrieval strategies
python eval/evaluate.py --strategy dense      # one strategy only
python eval/evaluate.py --strategy hybrid --verbose
python eval/evaluate.py --with-llm            # + citation precision & groundedness
```

The labeled set is [`eval/dataset.jsonl`](eval/dataset.jsonl) — 56 Turkish questions mapped
to the documents that should answer them (exercising cross-lingual retrieval).
Each question carries a `category` so the report shows *where* a strategy wins:

- **`lexical`** — names an exact code/endpoint (`RC-51`, `POST /v1/reversals`) → BM25's edge.
- **`semantic`** — Turkish paraphrase with little lexical overlap → the dense model's edge.
- **`confusable`** — describes an error *without* naming its code, so the answer is one of
  several near-identical ISO 8583 decline-code runbooks → where cross-encoder re-ranking
  earns its keep.

`--strategy all` prints a comparison table of recall@1/3/5 and MRR per strategy, plus an
MRR-by-category breakdown.

### Measured results (56 questions, 172 indexed chunks)

| Strategy | recall@1 | recall@3 | recall@5 | MRR |
|---|---|---|---|---|
| dense (baseline) | 0.607 | 0.696 | 0.714 | 0.656 |
| hybrid (dense + BM25) | 0.625 | 0.786 | 0.786 | 0.696 |
| **hybrid + re-rank** | **0.839** | **0.893** | **0.893** | **0.866** |

Every metric improves monotonically dense → hybrid → hybrid+rerank on this corpus. BM25
lifts *lexical* MRR 0.847 → 1.000, and the cross-encoder lifts *confusable* (near-identical
decline-code runbooks) 0.417 → 0.833 and *semantic* 0.594 → 0.797, for an overall MRR gain
of **+32%** over the dense baseline. Re-ranking ships **enabled by
default**: with CUDA torch it costs ~0.13s/query (measured on an RTX 4060, even with a
7B Ollama model resident); with CPU-only torch it costs ~6s/query instead — set
`RERANK_ENABLED=false` if that's too slow for your hardware. Full per-category numbers
and the CUDA setup are in [`DECISIONS.md`](DECISIONS.md) (D15).

## Docker

```bash
# Reuses your host's Ollama (GPU) by default; ensure the model is pulled first.
docker compose up --build          # -> http://localhost:7860
```

The container generates + ingests the corpus on first start; data persists in `./data`.
See [`docker-compose.yml`](docker-compose.yml) for a fully self-contained (CPU) Ollama
option.

## Internship topics covered

Data preparation & synthetic generation (`datagen.py`) · NLP preprocessing / sanitization
(`sanitization.py`) · prompt engineering (`rag/prompts.py`) · embeddings
(`rag/embeddings.py`) · vector databases & similarity search (`rag/vectorstore.py`) ·
hybrid retrieval & re-ranking (`rag/sparse_retriever.py`, `rag/retriever.py`,
`rag/reranker.py`) · RAG (`rag/engine.py`) · Gradio UI (`ui/app.py`) · evaluation
(`eval/`) · observability — structured logging, distributed trace-id propagation,
Prometheus metrics (`observability/`) · applied security — prompt-injection defense,
upload/XXE hardening (`security/`, D18–D19 in `DECISIONS.md`) · testing & coverage
(`tests/`) · documentation (this README + `DECISIONS.md`).

## Roadmap / future work

1. Better synthetic generator (LLM-assisted, more variety).
2. Retrieval quality: `bge-m3` embeddings; broader injection-guard coverage for
   Turkish-phrased attacks (see D18's documented limitation).
3. Answer streaming in the UI; conversation history.
4. Rate limiting at a reverse proxy (nginx/Traefik) in front of the app — the natural
   place for it once there's a real multi-user deployment (see D19).
5. Scaling toward ~50 users: swap Chroma → Qdrant, add caching, containerize the LLM.
6. Kubernetes deployment (intentionally out of scope for the MVP).
