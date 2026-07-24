# DECISIONS.md — Architecture & Design Decisions

A running log of important decisions: **what**, **why**, **alternatives**, **tradeoffs**.
Non-critical implementation assumptions are appended at the bottom as they are made.

---

## D1 — LLM provider abstraction, default = Ollama (local)
- **What:** RAG engine depends only on the `LLMProvider` interface. Concrete providers
  (Ollama, Anthropic, OpenAI) are selected via `LLM_PROVIDER`. Default is Ollama running
  `qwen2.5:7b-instruct` locally.
- **Why:** "Enterprise data must remain local" is a hard requirement; a local default
  keeps everything on-device. Qwen2.5-7B has strong Turkish and fits 8 GB VRAM. The
  abstraction keeps external APIs one env change away.
- **Alternatives:** Anthropic Claude API (best quality, but external + needs key),
  OpenAI (external + key). Both remain supported via the same interface.
- **Tradeoffs:** Local model quality < frontier APIs; first run requires
  `ollama pull qwen2.5:7b-instruct` (~4.7 GB). Accepted for a local-first MVP.
- **Provider transport:** providers call their HTTP APIs via `requests` rather than each
  vendor SDK. Keeps dependencies minimal and the three impls symmetric. Tradeoff: we
  hand-maintain small request payloads instead of using SDK conveniences.

## D2 — Embeddings: `intfloat/multilingual-e5-small` via sentence-transformers (local)
- **What:** Local multilingual embeddings with the E5 `query:` / `passage:` prefixing.
- **Why:** Dataset is **English**, UI/questions are **Turkish** → cross-lingual retrieval
  is required. multilingual-e5-small is small (fast on CPU), multilingual, and a strong
  baseline. Runs locally so no document text leaves the machine for embedding.
- **Alternatives:** `bge-m3` (stronger, heavier — noted as the upgrade path);
  English-only models (rejected: can't match Turkish queries to English docs);
  API embeddings (rejected: would send text off-device).
- **Tradeoffs:** sentence-transformers pulls in torch (large install). Accepted as the
  canonical, reliable path; `fastembed` (ONNX, torch-free) is a possible future swap.

## D3 — Vector store: ChromaDB (local, persistent)
- **What:** Chroma `PersistentClient` under `data/chroma`, cosine space, one collection.
- **Why:** Local, persistent, first-class metadata (needed for citations), minimal setup;
  ideal for a single-user MVP.
- **Alternatives:** FAISS (lightest, but no metadata layer → more code for citations);
  Qdrant (production-grade, scales to the ~50-user target, but adds a service).
- **Tradeoffs:** Chroma is less battle-tested at 50 users; migration to Qdrant is
  isolated behind the `VectorStore` interface if/when needed.

## D4 — RAG: minimal hand-rolled pipeline
- **What:** Own chunk → sanitize → embed → store → retrieve → prompt → generate → cite
  flow, no RAG framework.
- **Why:** Best demonstrates the internship concepts (embeddings, similarity search, RAG),
  fewest dependencies, easiest to read and maintain.
- **Alternatives:** LlamaIndex / LangChain (faster to assemble but hide the concepts and
  add heavy abstraction for a project this small).
- **Tradeoffs:** We implement chunking/retrieval ourselves; scope is deliberately small
  so this stays simple.

## D5 — Bilingual UX: English knowledge base, Turkish interface & answers
- **What:** Corpus authored in English (realistic payment API/runbook style); Gradio
  labels in Turkish; the assistant answers in Turkish and cites English sources.
- **Why:** Mirrors a Turkish enterprise using English technical documentation. Exercises
  the cross-lingual retrieval that D2 was chosen for.
- **Tradeoffs:** Slightly more prompt care (instruct the model to answer in Turkish from
  English context). Sanitization is language-independent, so no impact there.

## D6 — Packaging: pyproject + pip/venv (no uv)
- **What:** `pyproject.toml` (setuptools, src-layout), install via `pip install -e .`.
- **Why:** `uv` is not installed on the dev machine; pip/venv is portable and
  Docker-friendly. Entry scripts also add `src/` to `sys.path` so they run without an
  editable install.
- **Alternatives:** uv (faster, not installed); Poetry (extra tool, no benefit here).

## D7 — Config: pydantic-settings + `.env`
- **What:** Single typed `Settings` object, env-driven, validated at startup.
- **Why:** Type-safe config, 12-factor friendly, one obvious place for all knobs.
- **Alternatives:** raw `os.environ` (untyped), YAML config (another format to parse).

## D8 — Deployment: Dockerfile + docker-compose, no Kubernetes
- **What:** App container + optional Ollama service in compose; Chroma persisted via a
  volume. Kubernetes documented as future work only.
- **Why:** Compose covers a 1-user MVP and a small ~50-user pilot without orchestration
  overhead. Matches the brief ("K8s not required").

## D9 — Package layout by architectural layer
- **What:** Source is grouped into layer sub-packages: `llm/` (providers), `rag/`
  (embeddings, vectorstore, ingestion, logs, prompts, engine), `ui/` (Gradio), with
  `config`/`models`/`sanitization`/`service`/`datagen` as cross-cutting root modules.
  `tests/` mirrors this tree.
- **Why:** Makes the clean-architecture layers (already described in CLAUDE.md) visible in
  the filesystem; keeps related modules together; `tests/` mirroring source is easy to
  navigate. Depth is kept shallow (no one-file "package per class" sprawl).
- **Alternatives:** Flat modules in one package (fine, but the layering is implicit);
  deep per-concern packages (overengineered for this size).
- **Tradeoffs:** Intra-package imports use relative paths (`..models`); entry scripts
  import fully-qualified paths (`payment_assistant.rag.engine`). Both updated in one pass.

## D10 — Testing: pytest + coverage, fast and offline
- **What:** `pytest` with `pytest-cov`. Unit tests use in-memory fakes (`tests/conftest.py`)
  for embeddings/vector-store/LLM so the suite runs offline in seconds; vector-store tests
  use real Chroma in a temp dir; LLM providers are tested with a monkeypatched
  `requests.post`. `pytest --cov` reports ~99% statement coverage.
- **Why:** Deterministic, fast feedback; the clean interfaces make faking trivial. Coverage
  guards the security-critical and orchestration code against regressions.
- **Tradeoffs:** Launch glue (`ui/app.py:main`, the Gradio button wiring) is marked
  `# pragma: no cover` — it is exercised manually / via the integration eval, not unit
  tests.

## D11 — Hybrid retrieval: dense + BM25, fused with Reciprocal Rank Fusion
- **What:** A `Retriever` protocol with `DenseRetriever` (an *adapter* over the existing
  embedder + vector store), `BM25Retriever` (sparse), and `HybridRetriever` that runs both
  and fuses with RRF: `score(d) = Σ_r 1/(k + rank_r(d))`, `k=60`.
- **Why RRF:** it combines *ranks*, not scores, so it needs no normalization between a
  cosine similarity and an unbounded BM25 score — the failure mode of score-weighted
  fusion. It is also parameter-light (one constant) and robust when one retriever whiffs.
- **Why sparse at all:** embeddings blur exact tokens. Error codes (`PAY-6006`), endpoint
  paths, and English technical terms embedded in Turkish questions are precisely what BM25
  nails. Measured: lexical-category MRR **0.631 → 0.863**.
- **Alternatives:** weighted score fusion (needs normalization + tuning per corpus);
  sparse-only (fails on Turkish paraphrase); CombSUM/CombMNZ (same normalization problem).
- **Tradeoffs:** fusion slightly *hurts* purely semantic queries (MRR 0.385 → 0.346) by
  admitting lexical noise — an accepted trade for the much larger lexical gain. Both
  retrievers are config-gated so this is reversible.
- **Existing abstractions untouched:** `VectorStore` / `EmbeddingProvider` are unchanged;
  the new seam sits beside them.

## D12 — Cross-encoder re-ranking must be multilingual
- **What:** `CrossEncoderReranker` over `sentence_transformers.CrossEncoder`, default
  **`BAAI/bge-reranker-v2-m3`** (XLM-R based). Lazy-loaded, optional, `rerank_candidates=20`.
- **Why a cross-encoder:** the bi-encoder embeds query and document independently, which
  blurs near-identical documents. A cross-encoder scores the pair jointly and can separate
  the 9 structurally-identical error-code runbooks.
- **Why multilingual (important):** questions are **Turkish**, documents **English**. The
  commonly-suggested `cross-encoder/ms-marco-MiniLM-L-6-v2` is English-only and scores
  Turkish queries near-randomly — it would have *degraded* ranking rather than improved it.
  Cross-lingual capability is a hard requirement here, not a preference.
- **Tradeoffs:** ~2.2 GB one-time download and real per-query latency, so it ships
  **disabled by default** and is enabled via `RERANK_ENABLED=true`.
- **No new dependency:** `sentence-transformers` was already required for embeddings.

## D13 — The benchmark had to be rebuilt before it could measure anything
- **What:** Corpus grown 15 → **72 documents** (102 chunks) via a parameterized `datagen`
  v1; `chunk_size` 1200 → 500; eval set grown 10 → **50 questions** labeled by category
  (`lexical`, `semantic`, `confusable`).
- **Why:** the old benchmark was **saturated** — recall@3 and recall@5 were both 1.00, so
  total headroom across every metric was one question out of ten. Worse, re-ranking "the
  top 20 of 15 chunks" is a no-op. Any measured "improvement" would have been noise.
  Rebuilding the benchmark is what makes the retrieval work verifiable rather than
  decorative.
- **Design of the new set:** the 9 error-code runbooks are deliberately near-identical in
  structure and differ only in specifics — the exact case a bi-encoder blurs. The
  `confusable` category asks for one of them *without naming its code*, which is where a
  cross-encoder must earn its keep. Category labels let the report show *where* each
  strategy wins instead of one averaged number.
- **Note:** old and new numbers are not comparable — the corpus changed. The dense
  baseline is re-measured on the new benchmark.

## D14 — BM25 hand-rolled rather than `rank_bm25`
- **What:** ~40 lines implementing Okapi BM25 with an inverted index, in
  `rag/sparse_retriever.py`.
- **Why:** zero new dependencies, fully unit-tested, and consistent with D4's
  "minimal hand-rolled pipeline". The algorithm is simple enough that owning it costs less
  than auditing a dependency, and it makes the retrieval math explicit.
- **Alternatives:** `rank_bm25` (fine, but a dependency for ~40 lines); Elasticsearch
  (vastly out of scope for a local MVP).
- **Index source:** built from `CORPUS_DIR` via the existing `load_corpus` /
  `chunk_document` rather than by reading Chroma — this keeps `VectorStore` unchanged
  **and** inherits sanitization, so the sparse index cannot contain PII. Reading raw files
  directly would have silently bypassed the masking guarantee.

## D15 — CUDA torch + `RERANK_ENABLED=true` by default
- **What:** Switched the environment's `torch` from the CPU-only wheel to
  `torch==2.13.0+cu130` (same version, CUDA build, matching the RTX 4060's driver — see
  the cu130/cu129/cu128 wheel-availability note below). No application code changed:
  `CrossEncoderReranker(model_name, device=None)` already passed `device=None` to
  `sentence_transformers.CrossEncoder`, which auto-detects CUDA — GPU acceleration and
  the CPU fallback both "just work" from the same code path. `RERANK_ENABLED` default
  flipped `false` → `true` in `config.py` and `.env.example`.
- **Why:** re-ranking's quality win was already proven (D12, +64% MRR) but shipped
  disabled because it cost ~6s/query on CPU-only torch — too slow to default on. With
  CUDA it doesn't need that trade-off.
- **Measured, not assumed** (RTX 4060 Laptop, 8 GB VRAM):
  - Reranker alone: first call (model load) ~18.7s (one-time, lazy-loaded); warm calls
    average **0.14s**, ~2.28 GB VRAM.
  - Reranker **with `qwen2.5:7b-instruct` already resident in Ollama** (the real
    end-to-end scenario, not just the reranker in isolation): warm calls average
    **0.13s** — no measurable slowdown, and it did not fail or OOM, despite the two
    processes' combined footprint (~5.2–7.2 GB observed) leaving little headroom in the
    8 GB budget. This likely relies on Windows/WDDM's shared-GPU-memory fallback under
    pressure, which Linux/Docker deployments do not have — see the caveat below.
  - Both numbers are far under the "<1s" target and the previous ~6s CPU baseline
    (~43×).
- **Wheel selection:** chose `+cu130` specifically because it is the **same torch
  version** (`2.13.0`) already installed as `+cpu` — swapping only the build avoids any
  dependency resolution churn with `transformers`/`sentence-transformers`. The
  `cu129`/`cu128` indexes only go up to torch `2.9.0`/`2.11.0` respectively, which would
  have forced a downgrade; `cu130` was the only index carrying `2.13.0`. The RTX 4060's
  driver (CUDA UMD 13.3) is compatible with cu130.
- **Caveat — production/Docker:** the coexistence test above passed on Windows,
  possibly cushioned by WDDM's shared-GPU-memory spillover into system RAM, which masks
  tight VRAM budgets rather than failing loudly. A Linux container (the `docker-compose.yml`
  deployment path) has no such fallback and would OOM under the same combined load if
  the GPU is that tight. Production deployments sharing a GPU between the LLM and the
  reranker should monitor VRAM headroom directly (`nvidia-smi`) rather than relying on
  this result transferring to Linux.
- **Fallback:** `RERANK_ENABLED=false` remains the documented escape hatch for any
  environment without a working CUDA torch build (or with insufficient VRAM), where the
  ~6s/query cost isn't acceptable for interactive use.

## D16 — Structured logging via `ContextVar`, not threaded parameters
- **What:** A single `trace_id` (UUID, short form) is generated once per request in
  `RAGEngine.answer()` and bound to a `contextvars.ContextVar` for the call's duration
  (`observability.bind_trace_id`). A `logging.Filter` attached to the log handler
  (`TraceIdFilter`) injects the current value into every record that reaches it —
  including from nested layers (the retriever's embed/rerank steps, LLM providers) that
  never receive `trace_id` as a parameter. `configure_logging(log_format="json"|"text")`
  installs a `JsonFormatter` (default) or a readable console format, both trace-id-aware.
- **Why this shape:** the alternative — threading `trace_id` through every function
  signature in `rag/`, `llm/`, `security/` — would touch working, tested code across the
  whole call graph for a purely observational concern. `ContextVar` gives full
  propagation with zero signature changes anywhere except the one entry point
  (`RAGEngine.answer`), honoring "do not modify retrieval/LLM logic unless required."
- **Per-step timing:** `instrumented_step(name)` (in `observability/__init__.py`) wraps a
  stage, logs `{step, duration_ms, status, ...}` on completion (or `status="error"` +
  re-raise on exception), and records the same duration in a Prometheus histogram. Used
  at `sanitize` / `retrieve` / `generate` / `cite` (engine) and `embed` / `rerank`
  (retriever) — the six stages the requirement named, with `embed`/`rerank` nested inside
  `retrieve`'s span rather than flattened, since that is the real call structure.
- **JSON schema is a fixed allowlist, not `record.__dict__`:** `JsonFormatter` only
  emits a known set of extra fields (`step`, `duration_ms`, `status`, `chunk_count`,
  `redaction_count`, `token_count`, `reason`, `error`, …). This is a deliberate security
  boundary, not just tidiness: it makes it structurally impossible for a future
  `logger.info(..., extra={"query": raw_text})` mistake to leak into logs merely by
  existing — an unrecognized field is silently dropped rather than serialized. See D18's
  note on where the guard's log line sits, and the dedicated leak-scan suite (D-below).
- **Alternatives:** a third-party structured-logging library (`structlog`,
  `python-json-logger`) — rejected per "no heavy dependencies"; the JSON formatting
  needed here is ~15 lines of `json.dumps` over a fixed dict, not worth a dependency.
  Thread-local storage instead of `ContextVar` — rejected because this is `asyncio`- and
  thread-pool-safe by construction, `threading.local` is not.
- **Token usage:** logged best-effort from each provider's raw JSON response
  (`eval_count`/`prompt_eval_count` for Ollama, `usage.*` for Anthropic/OpenAI) as a
  plain `logger.info(..., extra={...})` call inside the provider, never surfacing through
  `LLMProvider.generate()`'s return type — so the interface (`str`) is unchanged and
  every existing call site is unaffected.

## D17 — Prometheus metrics: collection is always on, only the HTTP server is opt-in
- **What:** `prometheus_client` Counters/Histograms (`rag_requests_total`,
  `rag_stage_duration_seconds`, `rag_sanitization_redactions_total`,
  `rag_retriever_strategy_total`) live at module scope in `observability/metrics.py` and
  are updated unconditionally from `RAGEngine`/`retriever.py`. `METRICS_ENABLED=true`
  only decides whether `start_http_server(METRICS_PORT)` runs, exposing `/metrics`.
- **Why split it this way:** incrementing an in-memory counter costs microseconds, so
  there's no performance reason to gate collection — and *not* gating it means the flag
  can be flipped in a running deployment (or by an operator debugging locally) without
  losing any history. Only the network-facing HTTP server needs a flag: it's the part
  with a real cost/decision (do you want this port open at all).
- **No raw content in labels, by construction:** every label used is a fixed,
  low-cardinality string — a stage name, a sanitization category (`[EMAIL]`, `[CARD]`,
  …), a retriever strategy name (`dense`/`hybrid`/`hybrid+rerank`), a status word
  (`ok`/`blocked`/`empty`). None of these are ever derived from request content, so
  `/metrics` cannot leak query text or PII even in principle — there's no code path that
  *could* put a raw string there. Verified in `tests/security/test_pii_leak_scan.py`.
- **Retriever strategy label:** `DenseRetriever`/`HybridRetriever` gained a `.strategy`
  property (a plain string, computed from which of sparse/reranker are set) purely for
  this label. The engine reads it via `getattr(retriever, "strategy", "custom")` so a
  hand-rolled `Retriever` (e.g. a test fake) that doesn't define it degrades gracefully
  instead of raising.
- **Alternatives:** OpenTelemetry (full tracing + metrics) — significantly heavier for a
  single-process MVP; StatsD — needs a running agent, no local visualization story as
  simple as `/metrics` + `curl`. `prometheus_client` is a small, dependency-light,
  pull-based library that matches "lightweight custom endpoint" in the brief directly.
- **Dashboarding is a separate, optional overlay:** `docker-compose.observability.yml`
  (Prometheus + Grafana) is intentionally not part of the core `docker-compose.yml` — the
  main app image never gains a monitoring-stack dependency; you opt in by adding the
  overlay file.

## D18 — Prompt injection guard: deterministic regex, runs after sanitization
- **What:** `security/guard.py` exposes `inspect_query(query) -> (safe: bool, reason:
  str)`. Five fixed regex categories (instruction override, persona override, role-line
  injection, chat-template control tokens, system-prompt exfiltration attempts) are
  checked in order; the first match blocks the request with a hardcoded Turkish refusal
  message, skipping retrieval and the LLM call entirely (saving compute, not just
  refusing after the fact).
- **Pipeline placement — sanitize, THEN guard:** the guard inspects the
  already-PII-masked `retrieval_query`, never the raw question/log text. This means the
  one log line the guard emits on a block (`reason` category + `status="blocked"`,
  never the query itself) is guaranteed safe to log regardless of what triggered it —
  consistent with the project's existing "sanitize before anything downstream" rule
  rather than introducing a second, competing security ordering.
- **Why regex, not an LLM classifier:** matches the project's established pattern
  (`sanitization.py`) — deterministic, unit-testable, zero added latency, no
  reviewer-invisible model behavior. A classifier could catch more paraphrased attacks
  but would add cost, latency, and a new failure mode (the classifier itself becoming a
  target) for an internal tool where the LLM is a knowledge-base assistant, not an agent
  with side-effecting tools.
- **Known limitation (documented, not silently accepted):** patterns target common
  **English** jailbreak phrasing ("ignore previous instructions", etc.). A determined
  attacker phrasing the same instruction override in Turkish would evade every pattern
  here. Accepted because: (a) the domain is Turkish payment-support questions, where an
  English jailbreak phrase is itself anomalous and unlikely to appear by accident,
  keeping false positives near zero; (b) this is the same class of limitation
  `sanitization.py`'s regex approach already has and that DECISIONS.md already accepts
  elsewhere — deterministic rule-based defenses are inherently pattern-bounded. Extending
  coverage to Turkish-phrased attacks is straightforward future work (add patterns), not
  an architecture change.
- **False-positive tuning:** the prompt-leak pattern deliberately requires the phrase
  "system prompt" rather than the bare word "instructions" — the corpus and realistic
  support questions are full of legitimate "instructions" ("kurulum talimatları", "retry
  instructions"), which would have made a looser pattern unusable. Verified with explicit
  false-positive regression tests in `tests/security/test_guard.py`.
- **Default ON:** `INPUT_GUARD_ENABLED=true`. Unlike hybrid/rerank (which trade off
  latency/cost against quality), the guard's cost is a handful of regex matches — there's
  no reason to ship it off by default.

## D19 — Upload hardening: XML entity guard, size caps; rate limiting deferred
- **What:** three additions, all defense-in-depth, none touching retrieval/LLM logic:
  1. `rag/logs.py`: any `<!DOCTYPE` / `<!ENTITY` declaration is rejected by regex
     **before** `ET.fromstring` ever sees the text — the caller falls through to the safe
     raw-text fallback. Python's `ElementTree` does not resolve *external* entities
     (unlike `lxml`), so this isn't classic XXE file-read/SSRF, but internal entity
     expansion ("billion laughs") can still turn a few hundred bytes into gigabytes of
     memory from one parse call; rejecting outright is simpler and safer than trying to
     bound expansion.
  2. `service.AssistantService.ask_with_log_file`: rejects a file above
     `MAX_UPLOAD_BYTES` (default 2 MB) by checking `Path.stat().st_size` **before**
     reading it — an oversized upload never enters memory.
  3. `rag/engine.py`: an independent `_MAX_LOG_CHARS` (500,000) cap truncates `log_text`
     inside `RAGEngine.answer()` itself, regardless of caller. This is deliberately
     redundant with (2): it protects any *direct* caller of `ask()`/`answer()` — e.g. a
     future API layer that doesn't go through `ask_with_log_file`'s file-size gate —
     rather than relying solely on the one upload path that happens to exist today.
- **Why not `defusedxml`:** the task's "keep dependencies minimal" constraint plus the
  fact that Python's `ElementTree` is already immune to the *file-disclosure* half of
  XXE (only the entity-expansion DoS half applies) meant a 4-line regex guard closes the
  real gap without a new dependency.
- **Path traversal:** not separately hardened. `ask_with_log_file`'s `file_path` comes
  from Gradio's own upload handling today (a server-managed temp path, not a raw string
  the browser controls), so there is no current path from user input to an arbitrary
  filesystem path. Flagged here as a boundary risk to revisit *if* `AssistantService` is
  ever exposed through a future API layer that accepts a path directly — at which point
  it would need an explicit allow-listed-directory check, not before.
- **Rate limiting: deferred, not implemented.** The task explicitly marked this optional
  ("flag it if too complex"). A correct implementation needs per-client identity and
  either shared state across workers or sticky routing — neither exists yet in this
  single-process MVP, and getting it wrong (e.g. an in-memory counter that resets on
  every restart and doesn't coordinate across replicas) is worse than not having it,
  because it would look like protection without providing it. The standard, correct
  place for this is a reverse proxy (nginx/Traefik) in front of the app, which is also
  where the ~50-user production target would need one regardless of what the app itself
  does. Recorded here as a roadmap item, not silently dropped.

---

## Non-critical implementation assumptions
(Appended during implementation per the working agreement. Each is reversible.)

- **A1 — Chunking:** ~1200 characters with 150 overlap, paragraph-aware. Character-based
  (not token-based) to avoid a tokenizer dependency; comfortably under e5's 512-token
  limit. Configurable via `CHUNK_SIZE` / `CHUNK_OVERLAP`.
- **A2 — Retrieval depth:** `TOP_K=4` by default — enough context for grounded answers
  without overflowing the local model's context or diluting relevance.
- **A3 — Corpus format:** flat files in `data/corpus/`; `doc_type` inferred from filename
  prefix (`api_`, `runbook_`, `guide_`, `faq_`, `errorcodes_`, `log_`, `trace_`,
  `concept_`). Keeps ingestion trivial and metadata clean.
- **A4 — Sanitization point:** documents are sanitized once at load (before chunking);
  user questions and uploaded logs are sanitized at the start of the query path. Both
  guarantee no PII reaches embeddings, Chroma, or the LLM.
- **A5 — Citations:** context blocks are tagged `[S1]..[Sk]`; the model cites those tags,
  which the engine maps back to source documents shown in the UI.
- **A6 — Log parsing:** `logs.py` extracts a short summary (error codes / status /
  messages) from uploaded JSON/XML. In the query path the raw log is **sanitized first**
  (the guaranteed PII gate + accurate redaction reporting), and the summary is built from
  that clean text before augmenting the retrieval query. New module justified by being a
  distinct, reusable concern.
- **A7 — Synthetic generator:** template-based v0 (deterministic, no LLM) — a "working
  dataset" first, per the brief's priority order. Can be upgraded later.
- **A8 — Smoke-test model:** end-to-end verification used `qwen2.5:0.5b-instruct` (small,
  fast to pull) to prove the full loop live. The shipped default is `qwen2.5:7b-instruct`
  for real answer/citation quality; pull it with `ollama pull qwen2.5:7b-instruct`. Note:
  reliable `[S#]` citation emission depends on the model's instruction-following — the
  0.5b model is inconsistent at it; 7B (or an API provider) is reliable.

---

## Retrieval results (2026-07-24, 50 questions / 102 chunks)

`python eval/evaluate.py --strategy all`

| Strategy | recall@1 | recall@3 | recall@5 | MRR |
|---|---|---|---|---|
| dense (baseline) | 0.340 | 0.520 | 0.560 | 0.432 |
| hybrid (dense + BM25, RRF) | 0.440 | 0.540 | 0.600 | 0.500 |
| **hybrid + cross-encoder re-rank** | **0.620** | **0.800** | **0.840** | **0.707** |

MRR by question category — this is where the design shows its work:

| Strategy | lexical | semantic | confusable |
|---|---|---|---|
| dense | 0.631 | 0.385 | 0.042 |
| hybrid | **0.863** | 0.346 | 0.075 |
| hybrid + re-rank | 0.792 | **0.750** | **0.264** |

Reading the numbers honestly:
- **Hybrid** delivers exactly what BM25 was added for: lexical MRR 0.631 → **0.863**. It
  costs a little on semantic paraphrase (0.385 → 0.346) — the expected RRF trade of
  admitting lexical noise.
- **Re-ranking** is the decisive win: MRR 0.432 → **0.707** (+64% relative), recall@3
  0.52 → **0.80**. It more than repays the semantic dip (0.346 → **0.750**) and improves
  `confusable` 6×, confirming D12's premise that a cross-encoder separates near-identical
  runbooks a bi-encoder blurs.
- **It is not free or uniform:** re-ranking slightly *hurts* pure lexical queries
  (0.863 → 0.792), where BM25's exact match was already optimal. `confusable` remains low
  in absolute terms (0.264) — 9 near-identical runbooks are genuinely hard.
- **Latency:** ~6 s/query on this machine because the installed torch is **CPU-only**.
  That is why `RERANK_ENABLED` ships **false**: the quality win is large, but it is not
  usable interactively without a CUDA torch build. Enable it (with a GPU) for the gain.

## Verification (2026-07-24, MVP end-to-end)
- Unit tests: **94 passed**, **~99% statement coverage** (`pytest --cov`) across config,
  models, sanitization, embeddings, vectorstore, ingestion, engine, llm providers,
  service, ui, datagen, logs.
- Corpus generated (15 docs) and ingested (15 chunks) with the local embedding model.
- Retrieval eval (Turkish questions → English docs): **recall@3 = 1.00, MRR = 0.95**
  (re-confirmed after the layer reorganization).
- Live generation via Ollama produced Turkish answers; `[S#]` → source citation mapping
  works.
- Security verified on both paths: no raw PII in Chroma (ingestion), and query-path
  redactions correctly reported (card/email/TCKN/IP masked before the LLM).
- Gradio 6 UI builds successfully.
