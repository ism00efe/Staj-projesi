# CLAUDE.md — Payment Systems RAG Assistant

Persistent, every-session rules for this project. Read before making changes.

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
- The UI (`app.py`) must contain **no** business logic — it only calls the application
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
- UI: Gradio, Turkish labels; English knowledge base, Turkish answers
- Deploy: Dockerfile + docker-compose (no Kubernetes)
