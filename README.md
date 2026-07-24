# 💳 Payment Systems Knowledge & Log Analysis Assistant

A **RAG-based troubleshooting assistant for payment systems**. Ask a question or upload a
JSON/XML payment log; the assistant sanitizes the input, retrieves relevant material from
a local knowledge base, and generates **cited troubleshooting guidance** in Turkish.

> Internship MVP. The knowledge base ships with a **synthetic** English corpus, but the
> architecture lets you swap in real enterprise documents without changing the core
> system — you only point `CORPUS_DIR` somewhere else and re-ingest.

---

## Highlights

- **Local-first & privacy-preserving.** Embeddings and the vector DB run locally; the LLM
  defaults to a local Ollama model. Sensitive data is **masked before** it ever reaches
  embeddings, the vector store, or a prompt.
- **Provider-agnostic LLM.** Ollama (default), Anthropic, or OpenAI — chosen by an
  environment variable, behind one interface.
- **Cross-lingual retrieval.** English knowledge base, Turkish questions and answers,
  powered by a multilingual embedding model.
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

## Architecture

Clean, layered, and decoupled — the UI never contains business logic, and the RAG engine
depends only on small interfaces (embeddings / vector store / LLM), never on vendor SDKs.

```
src/payment_assistant/
  config.py         # typed settings (pydantic-settings + .env)
  models.py         # domain types: Document, Chunk, Citation, Answer, ...
  sanitization.py   # deterministic regex masking (security-critical)
  embeddings.py     # EmbeddingProvider protocol + sentence-transformers impl
  vectorstore.py    # VectorStore protocol + Chroma impl
  llm/              # LLMProvider protocol + ollama/anthropic/openai impls + factory
  logs.py           # JSON/XML log summarization
  ingestion.py      # load -> sanitize -> chunk -> embed -> index
  prompts.py        # versioned prompt templates
  rag.py            # RAGEngine (retrieve -> prompt -> generate -> cite)
  service.py        # application service (composition root; UI calls only this)
  app.py            # Gradio UI (presentation only)
  datagen.py        # synthetic corpus generator (v0)
scripts/            # generate_data.py, ingest.py, run_app.py
eval/               # dataset.jsonl + evaluate.py
tests/              # sanitization + log-parsing tests
```

## Prerequisites

- Python **3.11**
- [Ollama](https://ollama.com) running locally (for the default provider)
- ~5 GB disk for the default model, plus the embedding model (~0.5 GB, downloaded once)

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
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1200` / `150` | Chunking (characters) |
| `TOP_K` | `4` | Retrieved chunks per query |

## Security & sanitization

Deterministic, rule-based masking (never the LLM) runs before embedding and before any
LLM call. Masked categories: **credit cards** (Luhn-validated), **Turkish IDs / TCKN**
(checksum-validated), **IP addresses**, **emails**, **phone numbers**, and
**tokens/secrets** (JWT, Bearer, API keys). Checksum validation avoids false positives on
ordinary long numbers. Tests live in [`tests/test_sanitization.py`](tests/test_sanitization.py).

## Testing

```bash
pip install -e ".[dev]"
pytest                              # sanitization + log-parsing tests
```

## Evaluation

```bash
python eval/evaluate.py             # retrieval: recall@k, MRR (fast, no LLM)
python eval/evaluate.py --with-llm  # + citation precision & groundedness (needs a provider)
```

The labeled set is [`eval/dataset.jsonl`](eval/dataset.jsonl) — Turkish questions mapped to
the English source documents that should answer them (exercising cross-lingual retrieval).

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
(`sanitization.py`) · prompt engineering (`prompts.py`) · embeddings (`embeddings.py`) ·
vector databases & similarity search (`vectorstore.py`) · RAG (`rag.py`) · Gradio UI
(`app.py`) · evaluation (`eval/`) · documentation (this README + `DECISIONS.md`).

## Roadmap / future work

1. Better synthetic generator (LLM-assisted, more variety).
2. Retrieval quality: reranking, hybrid (keyword + vector) search, `bge-m3` embeddings.
3. Answer streaming in the UI; conversation history.
4. Scaling toward ~50 users: swap Chroma → Qdrant, add caching, containerize the LLM.
5. Kubernetes deployment (intentionally out of scope for the MVP).
