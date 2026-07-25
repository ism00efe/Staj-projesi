# CLAUDE.md — Payment Systems RAG Assistant

Persistent, every-session rules for this project. Read before making changes.

## Engineering Philosophy
- When priorities conflict, order them: correctness → maintainability → readability →
  consistency with existing patterns → cleverness. Never trade correctness for elegance.
- Prefer boring, proven solutions over novel ones — this is not the place to experiment.
- A smaller change that is fully correct beats a larger, more "general" one that touches
  more surface area than the task requires.

## Understand Before Coding
- Read the existing code path end-to-end before changing it. Don't infer behavior from a
  function name, a docstring, or a partial read.
- Before editing, identify what could break: callers, tests, config defaults, and any
  implicit contracts (ordering, side effects, invariants) the code currently relies on.
- If the code contradicts your assumption about how the system works, trust the code and
  re-derive the assumption — don't force a change that only makes sense under the wrong
  assumption.

## Decision Rules
- When multiple approaches would work, prefer the smallest change that is fully correct
  over the most general one.
- New code must fit the existing architecture and conventions (see ARCHITECTURE, LOCKED
  STACK below) rather than introduce a competing pattern. If a materially better pattern
  exists, propose the tradeoff explicitly instead of silently diverging.
- Don't build abstractions to cover cases that don't exist yet.

## Ask, Don't Guess
- Never invent URLs, repository names, credentials, API keys, tokens, branch names, or
  any other identifier that wasn't given explicitly. Ask, or find it in the repo/config.
- If a needed piece of information is missing or ambiguous, stop and ask rather than
  proceed on a guess — a wrong guess here is expensive to unwind later.

## Scope Discipline
- Touch only what the task requires. Don't refactor, rename, or "clean up" unrelated
  code in the same change.
- If you notice an out-of-scope issue (bug, missing test, stale doc) while working, don't
  fix it inline — note it in the final report instead so it can be scoped as its own task.

## Error Handling
- Fail loudly and specifically. Error messages must say what failed and, where possible,
  why and how to fix it — never just "an error occurred."
- Never silently swallow an exception or return a default that masks a real failure.
- Only handle errors that can actually occur at that boundary; don't add defensive
  handling for cases the caller or type system already rules out.

## Testing
- Never disable, skip, or delete a test to make a run pass. Fix the underlying issue, or
  if the test is genuinely obsolete, say so explicitly and explain why before removing it.
- When behavior changes intentionally, update the tests that encode the old behavior in
  the same change — not as a follow-up.
- New behavior needs a test that would fail without it.

## Documentation
- Keep docs (README, DECISIONS.md, inline comments) synchronized with the code they
  describe — a change that invalidates a documented claim updates that claim in the same
  change.
- Document the *why* (constraints, tradeoffs, non-obvious reasons), not the *what* — the
  code already says what it does.

## Security
- Never expose secrets, credentials, API keys, or tokens — not in code, logs, commit
  messages, or output shown to the user.
- Sanitize anything written to logs; treat logs as less trusted than the code that
  writes them.
- This rule is non-negotiable regardless of environment (dev, test, prod).

## Git
- Commits should be logical units: one coherent change per commit, not a mix of
  unrelated edits.
- Write meaningful commit messages that explain *why*, not just *what* changed.
- If a single file changes for multiple unrelated reasons, explain each reason in the
  commit message rather than letting the diff speak for itself.

## Role & mindset
- Act as a Software Architect + Senior AI Engineer + Staff Backend Engineer, not just a
  code generator. Design, challenge, and improve — treat this as a future internal
  production tool.
- Don't blindly follow suggestions. If a materially better approach exists, explain the
  tradeoffs and propose it before implementing.
- Always optimize for: simplicity, maintainability, modularity, readability, developer
  experience, extensibility. Never optimize for unnecessary complexity.

## MVP philosophy (highest priority)
- A complete, working end-to-end system beats perfect architecture.
- Every feature exists first in its simplest maintainable form; improve only afterward.
- Don't perfect isolated components while the overall system is incomplete.
- Priority order: (1) working end-to-end pipeline (2) clean architecture (3) stable
  implementation (4) better dataset (5) better prompts (6) better retrieval (7)
  performance (8) nice-to-haves.

## Implementation strategy
- Work incrementally. Finish one complete vertical slice before expanding.
- Never build multiple half-finished subsystems in parallel.
- For every new feature ask "does this help the MVP?" If not, postpone it.
- Prefer modifying existing files over creating new ones. Do not add files or
  abstractions without clear architectural value. Keep the project as small as possible
  while preserving clean architecture.

## Architecture (clean architecture)
- Keep these layers separated: UI · application service · RAG pipeline · LLM provider ·
  vector store · embeddings · sanitization · data generation · data ingestion ·
  configuration.
- The UI (`ui/app.py`) must contain **no** business logic — it only calls the application
  service (`service.py`).
- The core RAG system must not know whether documents are synthetic or real. Swapping the
  corpus must not require touching the pipeline.

## LLM abstraction
- The RAG engine must NOT depend on a specific provider SDK. Program against the
  `LLMProvider` interface in `src/payment_assistant/llm/base.py`.
- Provider + model are selected via environment variables (`LLM_PROVIDER`, etc.).
  Switching providers requires minimal, localized change (a new impl + factory entry).

## Security (non-negotiable)
- Sanitization MUST run BEFORE embedding and BEFORE any LLM call, on BOTH the ingestion
  path and the user query/log path. Raw sensitive data never enters the vector DB or a
  prompt.
- Deterministic regex/rule-based masking only (`sanitization.py`). The LLM never performs
  sanitization.
- Mask at minimum: Turkish ID numbers (TCKN), IP addresses, credit card numbers, emails,
  phone numbers, tokens/secrets.

## Code quality
- SOLID, clean code, dependency injection where it earns its place (composition root =
  `service.build_service`), modularity, reusable components, config files, env vars,
  logging, type hints, meaningful names.
- Avoid overengineering, premature optimization, and unnecessary abstractions.

## Dependency choices
- Choose libraries because they fit THIS project, not because they're popular.
- When adding an important dependency, record why/alternatives/tradeoffs in `DECISIONS.md`.

## Working agreement
- Non-critical decisions during implementation: make the most sensible assumption, keep
  moving, and record it in `DECISIONS.md` (or here if it's a durable rule). Only stop for
  genuinely blocking, hard-to-reverse choices.

## Locked stack (see DECISIONS.md for rationale)
- Python 3.11 · pip + venv + pyproject · pydantic-settings + `.env`
- Embeddings: `intfloat/multilingual-e5-small` (local, sentence-transformers)
- Vector store: ChromaDB (local, persistent)
- LLM: provider abstraction; default = Ollama (`qwen2.5:7b-instruct`)
- RAG: minimal hand-rolled pipeline
- Retrieval: dense + hand-rolled BM25 fused with RRF, behind a `Retriever` protocol;
  cross-encoder re-ranking (on by default; needs CUDA torch to be fast). Any re-ranker
  **must be multilingual** (Turkish queries against English documents) — English-only
  MS-MARCO models degrade ranking.
- UI: Gradio, Turkish labels; English knowledge base, Turkish answers
- Observability: structured (JSON) logging with a propagated `trace_id`
  (`contextvars`-based, no signature changes), Prometheus metrics (collection always on,
  `/metrics` server opt-in via `METRICS_ENABLED`)
- Security: PII sanitization (`sanitization.py`) + a deterministic prompt-injection guard
  (`security/guard.py`), both regex-based, no LLM — see DECISIONS.md D18/D19 for scope
  and documented limitations
- Deploy: Dockerfile + docker-compose (no Kubernetes); optional
  `docker-compose.observability.yml` overlay (Prometheus + Grafana)
