# 💳 Payment Systems Knowledge & Log Analysis Assistant

[![CI](https://github.com/ism00efe/Staj-projesi/actions/workflows/ci.yml/badge.svg)](https://github.com/ism00efe/Staj-projesi/actions/workflows/ci.yml)

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
  api/                # HTTP layer (transport only, no business logic)
    schemas.py        #   request/response models + Answer -> JSON mapping
    middleware.py     #   trace-id binding, body-size cap, rate limiter
    routes.py         #   POST /api/analyze, GET /api/health
    errors.py         #   one error envelope for every failure
    app.py            #   create_app(service, settings) + uvicorn launch glue
  ui/
    static/           #   index.html, style.css, app.js (vanilla, no build step)
vsix/                 # Visual Studio extension (C#) — see vsix/BUILD.md
scripts/              # generate_data.py, ingest.py, run_app.py
eval/                 # dataset.jsonl + evaluate.py
tests/                # mirrors the source tree; llm/ rag/ observability/ security/ + conftest fakes
```

## Interfaces

There is no second code path: the web UI and the Visual Studio extension are both thin
clients over the same two JSON endpoints — `POST /api/analyze` for questions/log analysis,
`POST /api/ingest` for adding a document to the knowledge base.

| Client | Where | Notes |
|---|---|---|
| Web UI | `http://127.0.0.1:7860/` | Two-panel page, Turkish labels, no framework; includes a "Bilgi Tabanını Güncelle" upload section |
| REST API | `POST /api/analyze`, `POST /api/ingest` | Interactive docs at `/docs` |
| Visual Studio | `vsix/` | VS 2022/2026 extension — builds clean; not yet run in an IDE, see [`vsix/BUILD.md`](vsix/BUILD.md) |

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

# 5) Run the app  ->  http://127.0.0.1:7860  (API docs at /docs)
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
| `MAX_UPLOAD_BYTES` | `2000000` | Reject log content above this size |
| `API_MAX_BODY_BYTES` | `5000000` | Whole-request body cap (checked before reading) |
| `API_RATE_LIMIT_ENABLED` | `true` | Per-client sliding-window limiter on `/api/*` |
| `API_RATE_LIMIT_REQUESTS` | `30` | Requests allowed per window, per client |
| `API_RATE_LIMIT_WINDOW_SECONDS` | `60` | Window length |
| `API_TRUSTED_PROXY_HOPS` | `0` | Proxy hops to trust in `X-Forwarded-For`; `0` = ignore it |
| `API_MAX_UPLOAD_BYTES` | `10000000` | Per-file cap for `POST /api/ingest` |
| `API_UPLOAD_RATE_LIMIT_REQUESTS` | `5` | Uploads allowed per window, per client |
| `API_UPLOAD_RATE_LIMIT_WINDOW_SECONDS` | `3600` | Window length for the upload limiter |

## API

One endpoint, used by every client:

```bash
curl -X POST http://127.0.0.1:7860/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "Bir ödeme insufficient funds hatası verdi, ne yapmalıyım?"}'
```

```json
{
  "answer": "RC-51 yetersiz bakiye anlamına gelir [S1] ...",
  "sources": [
    {"tag": "S1", "title": "Insufficient Funds Runbook", "doc_type": "runbook",
     "source_path": "runbook_rc51.md", "score": 0.91, "document_id": "runbook_rc51",
     "cited": true, "excerpt": "Retry after the customer funds the account ..."}
  ],
  "security_summary": {
    "blocked": false,
    "redactions": [{"label": "[CARD]", "count": 1}],
    "redaction_total": 1
  },
  "trace_id": "9b9df14e0a38"
}
```

`file_content` optionally carries log text. **The API never accepts a file path** — only
content — and unknown fields are rejected with a 422, so that is an enforced property
rather than a convention. `GET /api/health` returns the indexed chunk count and the
server's upload limits. Interactive docs: [`/docs`](http://127.0.0.1:7860/docs).

Adding a document to the knowledge base is a second endpoint, `multipart/form-data`:

```bash
curl -X POST http://127.0.0.1:7860/api/ingest \
  -F "file=@visa_reason_codes_2026.pdf"
```

```json
{
  "status": "ok",
  "filename": "visa_reason_codes_2026.pdf",
  "chunks_added": 12,
  "redactions": [],
  "redaction_total": 0,
  "trace_id": "9b9df14e0a38"
}
```

Accepts `.pdf`, `.txt`, `.md`, `.json`, `.xml`, `.log` (validated by content, not the
filename's extension — see **Security** below), up to `API_MAX_UPLOAD_BYTES` (10 MB
default). The file is sanitized through the exact same `sanitization.py` pipeline as
every query, chunked, embedded, and appended to the existing collection — it never
resets the knowledge base and never touches disk. A tighter rate limit applies
(`API_UPLOAD_RATE_LIMIT_*`, 5/hour default) than the general `/api/*` limit. See D25 in
`DECISIONS.md` for the design (including a known limitation: uploads are not yet
reflected in the BM25 sparse index until the process restarts).

Errors share one envelope, with Turkish user-facing messages:

```json
{"error": {"code": "rate_limited", "message": "Çok fazla istek gönderdiniz. ..."},
 "trace_id": "9b9df14e0a38"}
```

## Visual Studio extension

`vsix/` adds "Analyze with Payment Assistant" to the editor and Solution Explorer context
menus, with results in a dockable tool window. It never transmits anything without an
explicit action: with no selection it scans `.log`/`.json`/`.xml` for error codes and asks
which lines to send.

```bash
msbuild vsix/PaymentAssistant.sln /p:Configuration=Release /restore
# -> vsix/PaymentAssistant/bin/Release/PaymentAssistant.vsix
```

Builds clean (0 errors, 0 warnings) with Visual Studio Build Tools 2026 — the full IDE is
needed only to install and debug it.

> **Not yet run inside an IDE.** The build machine has no `devenv.exe`, so menu placement,
> the WPF tool window, and the `DTE` interop are compile-checked but never exercised.
> [`vsix/BUILD.md`](vsix/BUILD.md) spells out exactly what is and isn't verified.

## Observability

Every request gets a `trace_id`, bound once at the HTTP boundary and inherited by every
layer below it (engine, retriever, reranker, LLM provider) via a `contextvars.ContextVar`
— no function signature had to change to carry it. It's returned in every API response,
shown in the web UI (`İzleme kimliği`), and attached to every log line for that request,
so a user-reported issue can be traced end to end through the logs from one id:

```
9b9df14e0a38   sanitize     ok
9b9df14e0a38   embed        ok
9b9df14e0a38   rerank       ok
9b9df14e0a38   retrieve     ok
9b9df14e0a38   generate     ok
9b9df14e0a38   cite         ok
9b9df14e0a38   api.analyze  ok
```

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

**Upload hardening.** Log content above `MAX_UPLOAD_BYTES` (default 2 MB) is rejected, as
is any request body above `API_MAX_BODY_BYTES` (5 MB) — the latter before the body is read
at all. XML content with a `DOCTYPE`/`ENTITY` declaration is rejected before parsing
(defends against entity-expansion / "billion laughs" DoS — Python's `ElementTree` doesn't
resolve *external* entities, but internal expansion can still exhaust memory from a tiny
payload). See D19 in `DECISIONS.md` for the original reasoning.

**Knowledge-base upload validation.** `POST /api/ingest` checks a file's actual bytes, not
its filename: `filetype` verifies a claimed `.pdf` carries a real PDF signature (and
rejects any *other* recognizable binary signature outright, regardless of extension);
the plain-text formats have no signature of their own, so those must instead decode
cleanly as UTF-8. Content is sanitized through the identical `sanitization.py` pipeline
used for every query before it is chunked or embedded, capped at `API_MAX_UPLOAD_BYTES`
(10 MB default), rate-limited separately and more tightly than `/api/analyze`
(`API_UPLOAD_RATE_LIMIT_*`, 5/hour default), and never written to disk. See D25 in
`DECISIONS.md`.

**No file paths, by construction.** The API accepts only `file_content` text and rejects
unknown fields with a 422, so a client cannot ask the server to read a path. This closes
the path-traversal boundary D19 flagged for a future API layer — without needing the
allow-listed-directory check D19 anticipated (D22).

**Rate limiting.** A per-client sliding-window limiter guards `/api/*` (30 requests/60s
by default), returning 429 with `Retry-After`. It is deliberately **per-process and
best-effort**: it does not survive a restart or coordinate across replicas, and a reverse
proxy remains the right answer for a real multi-user deployment. See D23 for why this
supersedes D19's deferral. `X-Forwarded-For` is ignored unless `API_TRUSTED_PROXY_HOPS`
is set, and is then read from the right — trusting the leftmost entry would let any caller
forge its way around the limit.

**Errors never leak internals.** A 500 returns a generic Turkish message plus the trace
id; the exception text goes to the logs only. Validation failures report field *names*,
never the submitted values (FastAPI's default handler echoes them, which for this API
would mean handing raw user content straight back out).

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

The suite is fast and offline (~330 tests, ~30s) — models, Chroma, the LLM, and the
Prometheus HTTP server are replaced by in-memory fakes/monkeypatches (`tests/conftest.py`),
except the vector-store tests which run real Chroma in a temp dir. The API tests drive the
app through `TestClient`, so no server is started either. Coverage is ~99% of statements
across the package (launch glue excluded).

The C# extension under `vsix/` has no automated tests and is not built by CI (a VSIX needs
a Windows runner). It does build locally — see [`vsix/BUILD.md`](vsix/BUILD.md).

## CI/CD

Every push and pull request runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
on GitHub Actions:

1. **`test`** — installs the project (`pip install ".[dev]"`), then runs `ruff check .`
   (lint), `mypy src/` (type check), and `pytest --cov` (the full suite above). All three
   must pass.
2. **`build`** — only runs if `test` passes; builds the Docker image
   (`docker build -t payment-rag-assistant .`) to prove the container still builds. It
   does not push the image anywhere — that's future scope, not needed for an internship
   MVP. This job is also the only check that the web UI's static assets actually ship in
   the wheel: pytest puts `src/` ahead of site-packages, so no Python test can catch a
   packaging regression, and the `Dockerfile` asserts on the installed files instead.

`vsix/` is outside CI — `ubuntu-latest` cannot build a VSIX (D24).

Run the same checks locally before pushing:

```bash
pip install -e ".[dev]"
ruff check . && mypy src/ && pytest --cov
```

Design rationale (why ruff/mypy, why two separate jobs, why the HuggingFace cache) is in
[`DECISIONS.md`](DECISIONS.md) (D21).

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
`rag/reranker.py`) · RAG (`rag/engine.py`) · REST API design (`api/`) · front-end without
a framework (`ui/static/`) · IDE tooling / Visual Studio extensibility (`vsix/`) ·
evaluation (`eval/`) · observability — structured logging, distributed trace-id
propagation, Prometheus metrics (`observability/`) · applied security — prompt-injection
defense, upload/XXE hardening, rate limiting, XSS-safe rendering, content-based file-type
validation (`security/`, D18–D25 in `DECISIONS.md`) · testing & coverage (`tests/`) ·
documentation (this README + `DECISIONS.md`).

## Roadmap / future work

1. Better synthetic generator (LLM-assisted, more variety).
2. Retrieval quality: `bge-m3` embeddings; broader injection-guard coverage for
   Turkish-phrased attacks (see D18's documented limitation).
3. Install the Visual Studio extension in an IDE and verify it end to end (it builds, but
   has never been run); then add a `windows-latest` CI job for it — see
   [`vsix/BUILD.md`](vsix/BUILD.md).
4. Answer streaming (`text/event-stream` on the API, incremental render in the UI);
   conversation history.
5. Move rate limiting to a reverse proxy (nginx/Traefik) once there's a real multi-user
   deployment — the in-process limiter is per-process best-effort (see D23).
6. A `status` field on `Answer`, so clients no longer infer "blocked" from the refusal
   text (see D22); `AssistantService.ask_with_log_file` is now unused and can go with it.
7. Scaling toward ~50 users: swap Chroma → Qdrant, add caching, containerize the LLM.
8. Kubernetes deployment (intentionally out of scope for the MVP).
9. Rebuild (or incrementally update) the BM25 sparse index when a document is uploaded,
   so `/api/ingest` content gets the same lexical-match boost as the corpus loaded at
   startup, not just dense retrieval (see D25's documented limitation).
10. Screen uploaded document content for prompt-injection patterns, the same way queries
    already are — uploads are a new, less-trusted source of text that ends up in an LLM
    prompt as retrieved context, and `security/guard.py` does not see it today (see D25).
