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

## Verification (2026-07-24, MVP end-to-end)
- Unit tests: **19 passed** (sanitization incl. Luhn/TCKN/timestamp-not-IP; log parsing).
- Corpus generated (15 docs) and ingested (15 chunks) with the local embedding model.
- Retrieval eval (Turkish questions → English docs): **recall@3 = 1.00, MRR = 0.95**.
- Live generation via Ollama produced Turkish answers; `[S#]` → source citation mapping
  works.
- Security verified on both paths: no raw PII in Chroma (ingestion), and query-path
  redactions correctly reported (card/email/TCKN/IP masked before the LLM).
- Gradio 6 UI builds successfully.
