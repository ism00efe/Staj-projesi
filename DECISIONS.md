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
- **What:** Corpus authored in English (realistic payment API/runbook style); interface
  labels in Turkish; the assistant answers in Turkish and cites English sources.
  (The interface was Gradio when this was written; the decision itself is unchanged — see
  D22.)
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
  *(Updated by D22: `ui/` now holds static assets only and an `api/` layer was added. The
  layer-per-package principle is unchanged — the HTTP layer got its own package for the
  same reason.)*
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
  *(Updated by D22: that glue is now `api/app.py:main`, still the only `pragma: no cover`.
  The HTTP layer around it is unit-tested via `TestClient`, so the uncovered surface is
  smaller than it was — the routes, schemas, error handlers, and middleware are all
  covered.)*

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
  *(Resolved by D22. That API layer now exists and accepts only `file_content` text, with
  unknown fields rejected — so the risk is closed by construction and the allow-list check
  was never needed. `ask_with_log_file` has no production caller as of D22.)*
- **Rate limiting: deferred, not implemented.** The task explicitly marked this optional
  ("flag it if too complex"). A correct implementation needs per-client identity and
  either shared state across workers or sticky routing — neither exists yet in this
  single-process MVP, and getting it wrong (e.g. an in-memory counter that resets on
  every restart and doesn't coordinate across replicas) is worse than not having it,
  because it would look like protection without providing it. *(Superseded by D23, which
  quotes this reasoning and states what changed.)* The standard, correct
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

## D20 — Corpus v2: full rebuild into a realistic bilingual payment-systems KB
- **What:** `datagen.py`'s v1 corpus (72 generic-template documents — `PAY-1001`,
  `com.example.payments.*`) was **fully replaced**, not extended: `generate_corpus()`
  now clears every existing file in `CORPUS_DIR` before writing, so the old naming
  scheme can't leave orphaned documents behind when the scheme changes. The new corpus
  is 93 documents across the 10 families the brief specified (API reference, error-code
  catalogs, runbooks, FAQ, JSON/XML logs, stack traces, incident postmortems,
  conceptual overviews, configuration guides), modeled on real international payment
  standards (ISO 8583 MTIs and response codes, ISO 20022/SWIFT message types, EMV chip
  errors, Visa/Mastercard decline-code mapping) and the Turkish payment ecosystem (BKM,
  Troy, FAST), bilingual by design (English for international standards/APIs, Turkish
  for internal runbooks/regulations — matching how a Turkish bank actually operates).
  `eval/dataset.jsonl` was rebuilt in step: 56 questions (18 lexical / 32 semantic / 6
  confusable) against the new document IDs, same schema as before.
- **Why a full rebuild:** the brief was explicit that appending realistic content next
  to generic template content ("PAY-1001") would look inconsistent in a demo to a
  bank's payment team — the corpus needed to read as one coherent knowledge base, not
  two eras stitched together.
- **Fictional entities, confirmed with the user before writing content:** the bank
  ("Vera Bank"), its internal systems (Zirve POS, Kartlı Ödeme Motoru, Havale/Fast
  Bridge, etc.), and merchants (Marmara Elektronik, Ege Market, Anadolu Tekstil) are all
  invented — a real bank's name in fabricated failure logs and stack traces is cheap to
  avoid up front and expensive to unwind once embedded across ~30 files. Real, public
  infrastructure and standards (BKM, Troy, FAST, Visa, Mastercard, ISO 8583, ISO 20022,
  SWIFT, EMV, PCI DSS) are still referenced by name throughout — those are standards,
  not a specific company's fabricated internal bugs.
- **Content authorship & review disclosure (one place, not per-file):** this corpus was
  authored directly by the assistant (Claude), reviewed for factual plausibility against
  publicly documented standards while writing — ISO 8583 response-code semantics (RC-05
  "Do Not Honor" through RC-96 "System Malfunction"), MTI meanings, EMV terminology
  (ARQC, cryptogram, TVR), and the real, stable descriptions of BKM/Troy/FAST. A
  per-file marker was deliberately **not** added (see the plan-time decision with the
  user): that text would be embedded and indexed in every single chunk, adding
  boilerplate noise to the exact retrieval space this system is built to keep clean.
- **PII is synthetic, reused deliberately:** the same Luhn-valid test PAN
  (`4111 1111 1111 1111`) and an obviously-patterned checksum-valid TCKN
  (`10000000146`, repeating zeros — not a plausible real assignment) already used and
  tested in v1 carry forward, plus a second widely-published test PAN (Mastercard's
  `5555 5555 5555 4444`) and a second patterned TCKN for variety. Sprinkled into ~15 of
  the 93 files (log/trace samples), not every file — realistic production logs are
  mostly clean, which is itself part of the demo (see the "Verification" numbers below
  for exactly which categories got masked where).
- **Two real false positives found and fixed during authoring (not sanitization bugs —
  data-shape collisions with existing, correct sanitization patterns):**
  1. **RRN false-masked as `[PHONE]`.** ISO 8583's RRN (DE37) is a bare 12-digit field
     in a naive implementation; the sanitization phone pattern's optional
     country-code/area-code groups can fully consume any 9-14 digit run, so a
     pure-digit 12-character RRN is structurally indistinguishable from a phone number
     to that regex. Fixed at the source, not in `sanitization.py` (out of this phase's
     scope, and not obviously the right fix anyway — the pattern is correctly
     conservative): generated RRNs now include one letter (e.g. `260725F13281`),
     which is *more* realistic, not less — real-world RRN formats are
     processor-defined and commonly alphanumeric — and structurally breaks the
     phone regex's digit-only match.
  2. **Transaction ID false-masked as `[CARD]` (4 of 9 RC-code logs, by chance).** The
     card pattern tolerates dashes between digits; `TRX-20260725-NNNNN` forms a
     13-digit span across the dash (8-digit date + 5-digit sequence) that is
     occasionally Luhn-valid by pure chance, and Luhn-valid 13-19 digit runs are
     exactly what that pattern is supposed to catch. Fixed the same way: inserted a
     letter into the sequence portion (`TRX-20260725-A0111`), which breaks the
     digit-run structurally rather than relying on the Luhn coincidence not
     recurring.
  Both were caught by scanning every generated document's sanitized output against an
  "expected vs. unexpected mask" allowlist before considering the corpus done — the
  same discipline the PII leak-scan test suite already applies to the pipeline, applied
  here to the content itself.
- **Filename-prefix constraint honored:** every new document classifies under the 8
  prefixes `ingestion.py` already knows (`api_ errorcodes_ runbook_ faq_ log_ trace_
  concept_ guide_`) — `ingestion.py` itself was not touched, per the phase's explicit
  constraint. Configuration guides fit `guide_` naturally. Incident postmortems use a
  new `postmortem_` prefix, which falls through to the generic `"document"` doc_type —
  harmless, since doc_type is display/citation metadata only and never used for
  retrieval filtering.

## D21 — CI/CD: GitHub Actions, ruff + mypy, test/build split, no registry push
- **What:** `.github/workflows/ci.yml` runs on every push and PR. Job `test` installs
  the project (`pip install ".[dev]"`), then runs `ruff check .`, `mypy src/`, and
  `pytest --cov --cov-report=xml`. Job `build` runs only if `test` passes and runs
  `docker build -t payment-rag-assistant .` to prove the container still builds. Neither
  job pushes an image anywhere.
- **Why ruff:** one dependency replaces flake8 + isort + pyupgrade + a chunk of pylint,
  which matters for an intern-maintained repo — fewer tools to configure and explain.
  Enabled rule groups are deliberately narrow (`E`, `F`, `I`, `UP`, `B` — pyflakes,
  pycodestyle errors, import sort, pyupgrade, bugbear) rather than ruff's full rule set:
  wide-net linting on a repo this size mostly produces style bikeshedding, not caught
  bugs. `B` (bugbear) is the one that actually paid for itself in this pass — it caught
  two `zip()` calls without `strict=` in `reranker.py`/`vectorstore.py`, both cases
  where a silent length mismatch between parallel arrays would corrupt results rather
  than crash.
- **Why mypy, and why it's scoped to `src/`:** tests and eval scripts favor fakes,
  fixtures, and dynamic monkeypatching that fight static typing for little payoff;
  `src/` is where a wrong type actually reaches an LLM provider or the vector store in
  production. Real findings from the first run: an `_RC_CODES` dict typed
  `dict[str, str]` that actually carries `None` for card schemes with no equivalent
  code (RC-91 has no Mastercard code, RC-96 has no Visa code) — the call site already
  handled it (`rc['visa'] or '—'`), the annotation was just wrong; and a citation-vs-
  chunk variable in `ui/app.py` reusing the name `c` across two mutually exclusive
  branches, which mypy flags as a type conflict even though the branches never both
  run. Both were real (if low-severity) inaccuracies, fixed at the source rather than
  suppressed. The remaining findings — `requests.post(json=...)` and `chromadb`
  `Collection.add`/`query()` — are third-party stub over-precision (a JSON-serializable
  plain dict rejected because mypy can't prove every value is a `JsonType`; Chroma
  marking query-result fields `Optional` because `include` is technically dynamic, even
  though we always request all three) with no real bug underneath; those are narrow,
  commented `# type: ignore[code]` suppressions rather than defensive runtime asserts
  for cases that can't happen — consistent with this project's existing rule against
  validating what can't occur.
- **Why `test` and `build` are separate jobs, not steps:** `build` declares
  `needs: test`, so a broken test run stops the pipeline before spending time on a
  Docker build; a green pipeline in the Actions UI reads as two independent facts
  (code is correct; the container still builds) instead of one undifferentiated
  pass/fail.
- **Why the HuggingFace cache is present but currently inert:** the brief asked for it
  explicitly, and it costs nothing to keep warm — `actions/cache` on
  `~/.cache/huggingface` no-ops if nothing writes there. Today's test suite fakes out
  `SentenceTransformer`/`CrossEncoder` (see the Testing section of `DECISIONS.md`
  history / README), so no real model download happens in CI yet; the cache pays off
  the moment a future CI step runs `eval/evaluate.py` or a real smoke test against the
  actual embedding model.
- **Why no registry push:** out of scope for an internship MVP with no deployment
  target yet — `docker build` alone already answers the only question CI needs to
  answer right now ("does the image still build"). Pushing to a registry is a natural
  D-numbered follow-up once there's somewhere real to deploy to.

## D22 — HTTP API + vanilla web UI replace Gradio; a VS extension as a third client
- **What:** `api/` exposes `POST /api/analyze` (plus `GET /api/health`) as a thin
  controller over the unchanged `AssistantService`; the same process serves a plain
  HTML/CSS/JS page from `ui/static/` at `/`. Gradio and `ui/app.py` are gone. A Visual
  Studio extension (`vsix/`) is a third client over the identical endpoint.
- **Why not keep Gradio:** it owns the transport, the widget model, and the error
  surface, so there is no contract any other client can call — and its API moves between
  releases. This repo already carried a `[[tool.mypy.overrides]]` block written purely to
  stop chasing that movement; this change deletes it. Once a second and third client were
  required, "one JSON contract, three thin clients" was the only shape that avoided
  reimplementing the pipeline per client.
- **Why FastAPI:** pydantic is already a dependency (via pydantic-settings), so the
  schema layer costs nothing new; OpenAPI/`/docs` comes free, which matters for a team
  that has to integrate against this; and it is async-optional, so the blocking pipeline
  stays on a plain `def` handler that FastAPI dispatches to a threadpool. That last point
  is not incidental — `service.ask()` blocks for seconds (embed, re-rank, LLM), and an
  `async def` handler would have serialized every request including the page's own CSS.
- **Why vanilla JS and no npm:** the entire UI is presentation over one JSON endpoint.
  A build toolchain would roughly double the repo's tooling surface (node, a lockfile, a
  bundler, a second CI cache) to save nothing on three static files.
- **Why `create_app(service, settings)` and not `Depends` + `dependency_overrides`:**
  every seam in this codebase is constructor-injected with `build_service()` as the one
  composition root, and a module-level `app = create_app(build_service())` would run that
  root at *import* time — loading an embedding model just to import the package in a
  test. Explicit injection keeps the existing pattern and makes the test setup one line.
- **Trace ids: a real defect, found by running it.** `bind_trace_id()` minted a fresh id
  whenever called without one, so the API bound an id per request and `RAGEngine.answer()`
  immediately shadowed it with its own. Every request produced two ids, and a *failed*
  request's api-level log line could not be joined to the pipeline line that explained the
  failure. `bind_trace_id()` now inherits an already-bound id; an explicit id still wins,
  so a caller that means to start a distinct trace still can. Separately, unhandled
  exceptions are rendered by Starlette's `ServerErrorMiddleware`, which sits *outside*
  every user middleware — by then the context var has unwound, so every 500 told the user
  to quote trace id `"-"`. The id is now also written onto the ASGI scope, which survives
  the unwind. Both were invisible to unit tests and only showed up against a live server.
- **Why the `RequestValidationError` handler is mandatory:** FastAPI's default 422 body
  echoes the offending value back in `input`. Here that value is raw, unsanitized user
  content — a query or a log excerpt. The custom handler emits only dotted field paths,
  and `exc.errors()` is never handed to a logger.
- **This closes D19's open path-traversal question.** D19 flagged `ask_with_log_file`'s
  path parameter as a boundary risk "if `AssistantService` is ever exposed through a
  future API layer that accepts a path directly", and asked for an allow-listed-directory
  check at that point. The check turned out to be unnecessary: the API accepts only
  `file_content` text (the browser reads the file with `FileReader`, the extension with
  `File.ReadAllText`), and `extra="forbid"` rejects a stray `file_path` field with a 422.
  The risk is closed by construction rather than by validation. `ask_with_log_file` now
  has no production caller; it is left in place because `service.py` was out of scope for
  this phase, and noted as a removal candidate.
- **Why `blocked` is derived from a display string:** the engine signals a guard refusal
  only through `Answer.text == REFUSAL_MESSAGE`. That is a string comparison, but against
  a *public exported constant* already pinned by three tests in `tests/rag/test_engine.py`
  — not a copied literal. Every cleaner channel (`REQUEST_COUNT.labels(status="blocked")`)
  is metrics-only and unreachable per request. The clean fix is a `status` field on
  `Answer`, which needs a `rag/engine.py` change; recorded as the follow-up. The other two
  early-return cases are deliberately *not* string-matched — they have no constant and no
  test behind them, so matching them would be genuine brittleness.
- **Why empty input returns 200, not 422:** the engine already handles "no question and no
  log" with a Turkish message and a `status="empty"` metric. Short-circuiting in the
  controller would duplicate that string and silently lose the metric. 422 is reserved for
  requests that do not parse.
- **Why `/metrics` stays on its own port:** `build_service()` unconditionally starts the
  standalone exporter and `service.py` was out of scope, so mounting `/metrics` on the
  ASGI app would have meant *both* — or neutering `start_metrics_server` into a function
  whose docstring lies. Keeping it costs nothing, leaves `docker/prometheus.yml` and the
  compose files valid, and keeps the ops port separate from the user-facing one.
- **Why the client IP is never logged:** an IP address is one of the six categories
  `sanitization.py` exists to mask. The rate limiter keys on it in memory and never emits
  it, `_EXTRA_FIELDS` gained only `status_code`, and uvicorn's access log is disabled
  because its formatter renders the client address into every line. Two tests enforce this.
- **Packaging tripwire:** pytest puts `src/` ahead of site-packages, so *no* Python test
  can catch a missing `[tool.setuptools.package-data]` entry — the static assets would
  simply vanish from the Docker image. The guard is an assert in the `Dockerfile` after
  `pip install .`, which runs in CI's existing `build` job.

## D23 — In-process rate limiting, superseding D19's deferral
- **What:** a per-client sliding-window limiter (`api/middleware.py`) on the `/api` router,
  plus a 5 MB request-body cap. Configurable via `API_RATE_LIMIT_*`; on by default.
- **What changed since D19.** D19 declined this in strong terms: an in-memory counter
  "that resets on every restart and doesn't coordinate across replicas is worse than not
  having it, because it would look like protection without providing it." That reasoning
  was correct for what existed then and is now partly overtaken. Gradio's request queue
  previously provided incidental back-pressure; a plain JSON endpoint reachable by any
  HTTP client has none. The app is also still *deliberately* single-process — the
  in-memory Chroma client and the per-worker model load make `workers > 1` actively wrong
  — so "doesn't coordinate across replicas" describes a deployment that cannot currently
  exist. What remains valid from D19 is that a reverse proxy is the right answer for a
  real multi-user deployment; that stays on the roadmap. The limiter is documented as
  per-process best-effort in code, README, and `.env.example` so it is not mistaken for
  more than it is.
- **Why sliding window over fixed window:** a fixed window lets a client spend its whole
  budget at the end of one window and again at the start of the next — a "30 per minute"
  limit permits 60 requests in a couple of seconds across the boundary, which is precisely
  the burst the limit exists to stop.
- **Why the tracked-client cap:** without evicting stale buckets, a source rotating its
  address grows the dict without bound — turning the denial-of-service defense into a
  memory-exhaustion vector. `_MAX_TRACKED_CLIENTS` bounds it.
- **Why `X-Forwarded-For` is read from the right, and ignored by default:** everything to
  the left of your trusted hops is client-supplied and forgeable, so trusting the leftmost
  entry (the common mistake) would let any caller evade the limit with one header.
  `API_TRUSTED_PROXY_HOPS=0` means the header is ignored entirely, which is correct when
  nothing sits in front of the app — as in today's compose file.
- **Why a router dependency, not middleware:** middleware would count `GET /` and
  `/static/*` too, so one page load would rate-limit its own stylesheet.
- **Why `async def`:** it therefore runs on the event loop, where the limiter's deques
  cannot interleave. A plain `def` dependency would be handed to the threadpool and race.

## D24 — Visual Studio extension: classic VSSDK, shipped uncompiled
- **What:** `vsix/` adds a VS 2022/2026 extension with two context-menu commands and a
  dockable result tool window, calling the same `/api/analyze` endpoint.
- **Builds clean; runtime still unverified.** It was initially committed as
  *uncompiled*, on the belief that the machine lacked the VS SDK and the .NET Framework
  targeting pack. That was wrong — both checks had looked in the wrong place. The VSSDK
  MSBuild targets ship with *Build Tools* (under
  `MSBuild\Microsoft\VisualStudio\v18.0\VSSDK\`, not at the install root), and the v4.7.2
  targeting pack was present. `msbuild /p:Configuration=Release /restore` produces a valid
  VSIX with 0 errors and 0 warnings, and the generated `.pkgdef` shows the package,
  command table, tool window, and options page all registering correctly. Only one real
  defect surfaced: `await TaskScheduler.Default` needs
  `using Microsoft.VisualStudio.Threading`. What remains unverified is everything that
  only happens at runtime — menu placement, WPF/theme binding, `DTE` interop — because
  the machine has no IDE (`devenv.exe` genuinely absent) to install into. The distinction
  matters and is kept explicit in `vsix/BUILD.md`: "compiles and registers" is a real
  result, but it is not "works".
- **Why classic VSSDK over VisualStudio.Extensibility:** the newer model is SDK-style and
  .NET 8, which reads more modern, but its tool windows and dialogs must be built with
  Remote UI — thinly documented and easy to get subtly wrong. For code no compiler here
  can check, the heavily-documented template is the lower-risk choice, consistent with
  this project's "prefer boring, proven" rule.
- **Why `InstallationTarget [17.0,)`:** VS 2026 drives extension compatibility by API
  version, and that version is still 17.x, so a single manifest covers 2022 and 2026 and
  a future major does not force a republish.
- **Why `DataContractJsonSerializer` and not Json.NET:** Visual Studio loads its own
  Json.NET into the same process; an extension carrying a different version is a classic
  source of assembly-binding failures that only appear in someone else's IDE. The DTOs are
  simple enough that the in-box serializer costs nothing.
- **Data handling is the constraint that shaped the design:** no file watching, no
  background upload, nothing transmitted without a user action. The no-selection path
  scans for error codes and routes through a checkbox dialog; when it finds none it says
  so rather than falling back to sending the whole file — that silent fallback is the
  failure mode worth designing against. The Solution Explorer command does send a whole
  file, but only behind an explicit confirmation, because that is what the user clicked.
- **Why `ErrorCodeScanner` has no VS dependency:** it is the only class here with real
  logic rather than shell plumbing, so keeping it a plain static class leaves the one
  piece worth testing testable without an IDE.
- **Sources are shown, not opened.** `source_path` identifies a document in the server's
  knowledge base, not a file on the client's disk — for the synthetic corpus nothing at
  that path exists locally, and even against a real corpus the service may be on another
  host. The first version tried to open it and reported "kaynak dosya bu makinede
  bulunamadı" on failure, which turned the *normal* case into an error message and left
  the user with nothing. Selecting a source now shows its title, type, score and the
  excerpt the API already returns, plus one line saying where the document actually
  lives; opening is offered only when the path is rooted **and** exists locally. The
  alternative considered — having the client fall back to a web-UI source view — was
  rejected because no such view exists and neither the API nor the UI serves document
  bodies, so it would have meant a new endpoint to solve a display problem the existing
  `excerpt` field already solves.
- **Round-trip time is displayed** (`Yanıt süresi`), measured client-side around the
  whole call rather than taken from a server field, because the number that matters is
  the one the user waits through — including transport. It is shown on failure too: "it
  timed out after 180 s" and "it failed instantly" are different bug reports.
- **CI is untouched, for now:** `ubuntu-latest` cannot build a VSIX. Now that the build
  is known-good on Build Tools, a `windows-latest` job running the same
  `msbuild /restore` line is a cheap, worthwhile follow-up — it was only skipped
  originally because a job for an uncompiled project would have been red on day one.

## D25 — Web UI document upload for operational teams
- **What:** `POST /api/ingest` (multipart, one file) plus a collapsible "Bilgi Tabanını
  Güncelle" section in the web UI, so bank operations staff can add a new regulation or
  error-code document to the knowledge base themselves, without a developer dropping a
  file into `data/corpus/` and running `scripts/ingest.py`.
- **Why:** that manual step was fine while the corpus was synthetic and developer-owned;
  it stops being fine the moment the knowledge base needs to track real, frequently
  updated documents (a new Visa/Mastercard reason-code table, say) that only the
  operations team knows have changed.
- **Routed through `AssistantService`/`RAGEngine`, not wired directly in `routes.py`.**
  `RAGEngine` already privately holds the one embedder and one store instance the running
  process uses for every query; a second `ChromaVectorStore`/`SentenceTransformerEmbeddings`
  built inside the API layer would work (Chroma allows multiple handles to one collection)
  but would load a second embedding model into memory for no reason. `RAGEngine.ingest_document`
  and `AssistantService.ingest_document` are one-line delegations, the same shape as the
  existing `corpus_size()` / `ask()`, so the API layer stays a thin controller and every
  client goes through the one service entry point — consistent with this file's own
  "UI must contain no business logic" rule, which applies to `api/` the same way it
  applies to `ui/`.
- **`ingest_single_document` lives in `rag/ingestion.py`, not a new module.** It is the
  online counterpart to the existing offline `ingest()`: same sanitize → chunk → embed
  steps, reusing `chunk_document`, `_infer_title`, `_infer_doc_type` as-is. The only
  difference is `store.add()` on an already-open collection instead of `store.reset()` +
  a fresh directory read — not a different concern, so not a different file.
- **Content-based validation, not extension trust.** `filetype` (pure Python, no system
  `libmagic` dependency — the practical reason it beats `python-magic` on a Windows dev
  box) checks the actual byte signature: a claimed `.pdf` must carry a real `%PDF-`
  header, and content matching some *other* binary signature (image, archive, ...) is
  rejected outright regardless of its extension. Plain-text formats (`.md/.txt/.json/
  .xml/.log`) have no signature of their own — `filetype.guess` correctly returns `None`
  for them — so those are instead validated by requiring a clean UTF-8 decode, which
  rejects binary garbage renamed with a text extension the same way. `pypdf` (pure
  Python, read-only, no compiled dependency) extracts the text layer for real PDFs.
- **Never touches disk.** Starlette's `UploadFile` already spools to memory (spilling to
  an auto-cleaned temp file only past its own size threshold) and processing runs
  entirely on the in-memory `bytes` it returns — there was no need to add explicit
  `tempfile` handling to get the "never write to `data/corpus/`" guarantee.
- **Two independent size limits needed `BodySizeLimitMiddleware` to grow a per-route
  override.** The existing `API_MAX_BODY_BYTES` (5 MB) bounds the whole `/api/analyze`
  JSON envelope; a real PDF needs more room than that. Raising the global cap would have
  loosened the DoS bound on every other route for a limit only this one needs, so
  `route_overrides` lets `/api/ingest` alone use the larger `API_MAX_UPLOAD_BYTES`
  (10 MB default). The route handler *also* re-derives the same check against the file's
  exact decoded size — provably unreachable over real HTTP while both layers use the same
  number (the multipart envelope can only be ≥ the file it carries), kept anyway as the
  same belt-and-suspenders shape `_reject_oversized_log` already uses for `/api/analyze`,
  so this route does not silently depend on transport wiring it does not own.
- **A separate, much tighter rate limit (5/hour default), layered on top of the general
  one, not instead of it.** Ingesting a file costs far more per request (embedding +
  chunking + a Chroma write, on top of everything `/api/analyze` already does) and,
  unlike an answer, permanently adds to what every future query can retrieve. A second
  `RateLimiter` instance with its own bucket, attached as a route-level dependency on
  `/ingest` alongside the router-wide one, keeps the two budgets from sharing state.
- **The filename is sanitized too, and — unusually — logged.** `source_path`/title
  fallback are built from the filename, and it is operator-supplied rather than
  developer-curated, so it goes through `sanitize_text` exactly like the document body
  before either is stored. It is also the one piece of "user content" this API logs
  (`upload_filename` in `_EXTRA_FIELDS`): unlike a query or log excerpt, a filename is
  named by a trusted internal operator, and knowing *which* document changed the shared
  knowledge base is the entire point of an audit trail for this endpoint. Found and fixed
  during testing: the field is named `upload_filename`, not `filename` — `filename` is a
  reserved `logging.LogRecord` attribute (the source `.py` file of the log call itself),
  and passing it via `extra=` raises `KeyError` at the first real upload once
  `configure_logging()` sets the root logger to `INFO`. An ad hoc smoke test missed this
  because it never called `configure_logging()`, so the `INFO` record was filtered out
  before `extra` was ever validated; the real regression test asserts against
  `caplog.records`, which runs the record through the same construction path production
  logging does.
- **Known limitation: the sparse (BM25) index does not see uploads.** `HybridRetriever`'s
  BM25 side is built once at startup from `corpus_dir` on disk (`build_bm25_from_corpus`);
  an upload is added only to the live Chroma collection, per the "never write to
  `data/corpus/`" constraint above. A newly uploaded chunk is therefore immediately
  retrievable via the dense side and via RRF fusion (which unions rather than intersects
  the two rankings), just without a BM25 lexical-match contribution until the process
  restarts against a repopulated corpus directory — a real but modest degradation (loses
  the exact-match boost for e.g. an error code in the new document, not the ability to
  retrieve it at all), not a correctness bug. Rebuilding the in-memory BM25 index on every
  upload was considered and rejected for this MVP: it is O(corpus size) work on every
  upload for a gap that only affects lexical-match ranking, not recall.
- **Known follow-up, not addressed here: prompt injection via uploaded corpus content.**
  `security/guard.py` inspects the *query* before retrieval; it has never inspected
  *corpus* content, which was safe while every document was developer-curated. This
  feature changes that trust boundary — an uploaded document's text is later placed
  verbatim into an LLM prompt as retrieved context, so adversarial instructions embedded
  in an uploaded file are not screened by anything today. Not in scope for this change
  (not requested, and the right screening point — the guard, at ingest time, at prompt-
  build time — is a real design question of its own), but worth scoping as a follow-up
  now that the corpus has a second, less-trusted source of content.

## D26 — Three-tier benchmark methodology; `full-quality` measured on Colab, not locally
- **What:** `scripts/benchmark.py` measures the pipeline at three fixed configurations
  against the labeled `eval/dataset.jsonl` set: `fast` (dense-only retrieval,
  `qwen2.5:0.5b-instruct`), `balanced` (hybrid dense+BM25 retrieval, RRF-fused, no
  re-ranker, `qwen2.5:7b-instruct`), and `full-quality` (hybrid + cross-encoder re-rank,
  `qwen2.5:7b-instruct`). Each tier reuses `eval/evaluate.py`'s own scoring functions for
  retrieval metrics (recall@1/3/5, MRR) so the two scripts can never silently disagree,
  then runs one `AssistantService.ask()` call per question end-to-end (sanitize -> guard
  -> retrieve -> rerank -> generate -> cite), timing each individually for median/p95
  latency and scoring citation precision/groundedness the same way `eval/evaluate.py
  --with-llm` does. Writes a Markdown comparison table to `benchmark_results.md`.
- **Why three tiers, not one number.** "The RAG pipeline's latency/quality" isn't one
  number -- it depends on which retrieval/re-rank/LLM-size knobs are set, and every knob
  here is independently configurable (`HYBRID_ENABLED`, `RERANK_ENABLED`, `OLLAMA_MODEL`).
  Three fixed, named configurations give a reader something concrete instead of an
  unbounded knob space: cheapest-viable (`fast`), a mid-range config with no re-ranker
  (`balanced`), and the project's actual default / best-measured-quality config
  (`full-quality` -- hybrid + re-rank measures MRR 0.866 vs hybrid-only's 0.696, per the
  retrieval results already in this file).
- **`full-quality` is measured on a Colab T4 (`colab/colab_benchmark.ipynb`), not the
  local RTX 4060 Laptop (8 GB).** The cross-encoder re-ranker (~2.2 GB, D15) stacked on a
  resident 7B Ollama model is a documented risk on an 8 GB card; a local run of exactly
  this tier crashed the machine outright on 2026-07-26 (see below) -- not a graceful CUDA
  `OutOfMemoryError` the script's own `_looks_like_oom` handling could catch and report as
  a row, but something that killed the process itself before it even finished
  retrieval-quality scoring for the tier, let alone reached any LLM call. Rather than keep
  retrying against hardware that is already known to be tight for this configuration,
  `full-quality` numbers come from a free Colab T4 (16 GB) runtime instead, via the
  self-contained notebook, which runs the exact same `scripts/benchmark.py --tier
  full-quality` so the row is directly comparable. The local `benchmark_results.md`
  records `full-quality` as not run locally (OOM risk on 8 GB), pointing to the Colab row.
- **`--tier` accepts multiple values** (`--tier fast balanced`), added alongside this
  decision so a hardware-constrained machine can run everything it safely can in one
  invocation (one shared embedder/store load) while excluding `full-quality` outright,
  instead of needing three separate single-tier invocations or a code fork.
- **The crash, for the record:** running all three tiers locally on 2026-07-26, `fast`
  and `balanced` both completed cleanly (56/56 questions each); `full-quality` loaded the
  reranker fine and got partway through its retrieval-scoring pass (before any LLM call
  for that tier) when the process was killed outright -- no Python exception, no logged
  OOM, the log simply stops mid-batch. Whatever killed it took the whole session with it.
  This decision (Colab for `full-quality`) is the direct response; D27's
  `EMBEDDING_DEVICE=cpu` default is related but separate headroom, not a fix for this
  specific crash -- the embedder was resident on GPU during the two tiers that completed
  without any issue.

## D27 — Embedding model defaults to CPU, not auto-detected CUDA
- **What:** `EMBEDDING_DEVICE` (`.env.example`, `Settings.embedding_device`, default
  `"cpu"`) is threaded through every `SentenceTransformerEmbeddings(...)` call site
  (`service.py`, `scripts/ingest.py`, `scripts/benchmark.py`, `eval/evaluate.py`) into the
  constructor's existing `device` keyword, which every call site previously left as
  `None` — sentence-transformers' own auto-detect, which silently picks `cuda:0` whenever
  a GPU is visible.
- **Why:** on an 8 GB laptop GPU, the resident 7B Ollama model already uses most of the
  VRAM budget, and the cross-encoder reranker (~2.2 GB, D15) on top of that is a
  documented OOM risk. `multilingual-e5-small` is small and is not the proven cause of any
  specific measured crash (see D26), but it was one more process competing for the same
  pool for a task that was never latency-sensitive enough to need the GPU — single short
  queries/chunks, not large batches. Cheap insurance after a session that crashed the
  machine outright running the benchmark's `full-quality` tier.
- **Measured (RTX 4060 Laptop, 8 GB; Ollama resident, idle):** baseline GPU memory ~1.71 GB
  used. Loading the E5 model and running one `embed_query` with the new default
  (`EMBEDDING_DEVICE=cpu`): still ~1.70 GB — no measurable change. Forcing the old,
  implicit behavior (`EMBEDDING_DEVICE=cuda`): ~2.30 GB — the embedding model alone costs
  ~600 MB of VRAM once loaded on this hardware, now freed by default.
- **Still overridable per deployment.** `EMBEDDING_DEVICE=cuda` restores the old behavior
  on hardware with headroom to spare (a desktop GPU, or a machine not also running the
  LLM/reranker locally); CPU inference for this model is fast in absolute terms (small
  model, small batches — unlike the reranker, where D15 measured CPU at ~46x slower than
  CUDA), so the default costs little even where the override isn't needed.

---

## Retrieval results (2026-07-25, corpus v2 — 56 questions / 172 chunks)

`python eval/evaluate.py --strategy all`, run against the rebuilt corpus (93 documents).
Superseded the 2026-07-24 numbers below, which were measured against the now-replaced
72-document v1 corpus and are kept only as a historical record.

| Strategy | recall@1 | recall@3 | recall@5 | MRR |
|---|---|---|---|---|
| dense (baseline) | 0.607 | 0.696 | 0.714 | 0.656 |
| hybrid (dense + BM25) | 0.625 | 0.786 | 0.786 | 0.696 |
| **hybrid + re-rank** | **0.839** | **0.893** | **0.893** | **0.866** |

MRR by category — the confusable set (ISO 8583 RC-code runbooks + ARQC-vs-cryptogram
pairs, described by symptom without naming the code) is exactly where re-ranking is
supposed to earn its keep, and does:

| Strategy | lexical | semantic | confusable |
|---|---|---|---|
| dense | 0.847 | 0.594 | 0.417 |
| hybrid | 0.880 | 0.615 | 0.583 |
| hybrid + re-rank | 1.000 | 0.797 | **0.833** |

Every metric improves monotonically dense → hybrid → hybrid+rerank on this corpus —
cleaner differentiation than v1 saw (where hybrid cost a small amount of semantic MRR as
a documented tradeoff); the richer, more genuinely confusable RC-code family gives both
BM25 and the cross-encoder more real signal to work with.

---

## Retrieval results (2026-07-24, 50 questions / 102 chunks) — historical, v1 corpus

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
