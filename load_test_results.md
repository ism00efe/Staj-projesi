# Load Test Results

Target: `http://127.0.0.1:7860`. Query mix drawn round-robin from `eval/dataset.jsonl` (lexical / semantic / confusable).

## POST /api/analyze (full pipeline: sanitize -> guard -> retrieve -> rerank -> generate -> cite)

| Concurrency | Requests | Duration (s) | RPS | Median (ms) | p95 (ms) | p99 (ms) | Error Rate |
|---|---|---|---|---|---|---|---|
| 1 | 1 | 13.38 | 0.07 | 13376 | 13376 | 13376 | 0% |
| 5 | 5 | 88.89 | 0.06 | 56009 | 86666 | 88426 | 0% |
| 10 | 10 | 155.47 | 0.06 | 104862 | 150237 | 154364 | 0% |

## GET /api/health (transport/API overhead only -- no retrieval or LLM call)

| Concurrency | Requests | Duration (s) | RPS | Median (ms) | p95 (ms) | p99 (ms) | Error Rate |
|---|---|---|---|---|---|---|---|
| 1 | 1 | 0.02 | 41.45 | 24 | 24 | 24 | 0% |
| 5 | 5 | 0.11 | 46.00 | 85 | 96 | 97 | 0% |
| 10 | 10 | 0.17 | 58.39 | 125 | 143 | 146 | 0% |

**Reading the error rate column:** the server's default rate limiter allows 30 requests / 60 s per client (`API_RATE_LIMIT_REQUESTS` / `API_RATE_LIMIT_WINDOW_SECONDS`), shared across every `/api/*` route including `/api/health`. This script is one client, so 429s at higher concurrency reflect that configured protection working as intended, not the pipeline failing -- see DECISIONS.md D23 and D26.
