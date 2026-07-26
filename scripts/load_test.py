"""Concurrent load test against a running server (local or remote, via --url).

Usage:
  python scripts/load_test.py                                  # full sweep, localhost
  python scripts/load_test.py --url http://localhost:7860 --users 10
  python scripts/load_test.py --users 1 5 10 --output out.md

Fires N concurrent requests (one per "user") at POST /api/analyze, for each
concurrency level in --users (default: 1 5 10 20 50) -- then repeats the same sweep
against GET /api/health, a request that does no retrieval or LLM work at all, so its
numbers isolate pure HTTP/transport overhead from full-pipeline latency.

Queries are drawn round-robin from `eval/dataset.jsonl` (lexical / semantic /
confusable -- the same labeled set `eval/evaluate.py` and `scripts/benchmark.py` use),
so every concurrency level sees a realistic question mix instead of one repeated string.

IMPORTANT -- the built-in rate limiter (DECISIONS.md D23) is deliberately NOT bypassed
or raised here: it is part of what a load test should measure, not something to work
around. By default the server allows 30 requests / 60 s **per client**
(`API_RATE_LIMIT_REQUESTS` / `API_RATE_LIMIT_WINDOW_SECONDS` in .env), shared across
every `/api/*` route including `/api/health` -- this script is a single client, so any
concurrency level whose cumulative requests exceed that budget within the window WILL
see 429s by design. That is a real, correct finding, not a bug in this script or the
server. A one-time `--cooldown-seconds` pause (default 65 s) runs between the
`/api/analyze` sweep and the `/api/health` sweep so the second sweep starts from a
clean budget instead of inheriting the first sweep's exhaustion -- that is what makes
the two comparable ("isolated"). To measure pipeline capacity above the configured
protection, raise `API_RATE_LIMIT_REQUESTS` / `_WINDOW_SECONDS` in the target server's
own `.env` and restart it; this script does not do that for you.

Writes a Markdown report to `load_test_results.md` (or --output).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import cycle
from pathlib import Path

import httpx
import numpy as np

_DEFAULT_USERS = [1, 5, 10, 20, 50]
_DATASET = Path(__file__).resolve().parent.parent / "eval" / "dataset.jsonl"
_ANALYZE_TIMEOUT = 200.0  # a full pipeline call with a 7B LLM can legitimately take tens of s
_HEALTH_TIMEOUT = 30.0


def load_questions() -> list[str]:
    """The same labeled questions eval/evaluate.py and scripts/benchmark.py score against."""

    questions = []
    for line in _DATASET.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            questions.append(json.loads(line)["question"])
    if not questions:
        raise SystemExit(f"No questions found in {_DATASET}")
    return questions


@dataclass
class LevelResult:
    concurrency: int
    total_requests: int
    duration_s: float
    rps: float
    median_ms: float
    p95_ms: float
    p99_ms: float
    error_rate: float
    errors_by_kind: dict[str, int]


async def _one_request(
    client: httpx.AsyncClient, method: str, path: str, body: dict | None, timeout: float
) -> tuple[float, str | None]:
    """One request. Returns (latency_seconds, error_kind) -- error_kind is None on 2xx/3xx."""

    start = time.perf_counter()
    try:
        if method == "GET":
            resp = await client.get(path, timeout=timeout)
        else:
            resp = await client.post(path, json=body, timeout=timeout)
        elapsed = time.perf_counter() - start
        return elapsed, (str(resp.status_code) if resp.status_code >= 400 else None)
    except httpx.TimeoutException:
        return time.perf_counter() - start, "timeout"
    except httpx.ConnectError:
        return time.perf_counter() - start, "connection_error"
    except httpx.HTTPError as exc:
        return time.perf_counter() - start, type(exc).__name__


async def run_level(
    base_url: str,
    path: str,
    method: str,
    concurrency: int,
    question_cycle: Iterator[str],
) -> LevelResult:
    """Fire `concurrency` requests at once (one per simulated user) and time the batch."""

    timeout = _ANALYZE_TIMEOUT if method == "POST" else _HEALTH_TIMEOUT
    if method == "POST":
        bodies: list[dict | None] = [{"query": next(question_cycle)} for _ in range(concurrency)]
    else:
        bodies = [None] * concurrency

    async with httpx.AsyncClient(base_url=base_url) as client:
        start = time.perf_counter()
        results = await asyncio.gather(
            *(_one_request(client, method, path, body, timeout) for body in bodies)
        )
        wall_time = time.perf_counter() - start

    latencies_ms = [r[0] * 1000 for r in results]
    errors_by_kind: dict[str, int] = {}
    for _, kind in results:
        if kind is not None:
            errors_by_kind[kind] = errors_by_kind.get(kind, 0) + 1
    error_count = sum(errors_by_kind.values())

    return LevelResult(
        concurrency=concurrency,
        total_requests=len(results),
        duration_s=wall_time,
        rps=len(results) / wall_time if wall_time > 0 else 0.0,
        median_ms=float(np.percentile(latencies_ms, 50)),
        p95_ms=float(np.percentile(latencies_ms, 95)),
        p99_ms=float(np.percentile(latencies_ms, 99)),
        error_rate=error_count / len(results),
        errors_by_kind=errors_by_kind,
    )


async def run_sweep(
    base_url: str,
    path: str,
    method: str,
    users: list[int],
    question_cycle: Iterator[str],
    label: str,
) -> list[LevelResult]:
    levels = []
    for n in users:
        print(f"\n{label}: {n} concurrent user(s)...")
        result = await run_level(base_url, path, method, n, question_cycle)
        errors_note = f" errors={result.errors_by_kind}" if result.errors_by_kind else ""
        print(
            f"  {result.total_requests} req in {result.duration_s:.2f}s -> "
            f"{result.rps:.2f} RPS, median {result.median_ms:.0f} ms, "
            f"p95 {result.p95_ms:.0f} ms, error rate {result.error_rate:.0%}{errors_note}"
        )
        levels.append(result)
    return levels


def format_table(levels: list[LevelResult]) -> str:
    header = (
        "| Concurrency | Requests | Duration (s) | RPS | Median (ms) | p95 (ms) | "
        "p99 (ms) | Error Rate |"
    )
    separator = "|---|---|---|---|---|---|---|---|"
    rows = [header, separator]
    for lv in levels:
        rows.append(
            f"| {lv.concurrency} | {lv.total_requests} | {lv.duration_s:.2f} | "
            f"{lv.rps:.2f} | {lv.median_ms:.0f} | {lv.p95_ms:.0f} | {lv.p99_ms:.0f} | "
            f"{lv.error_rate:.0%} |"
        )
    return "\n".join(rows)


def write_report(
    url: str, analyze_levels: list[LevelResult], health_levels: list[LevelResult], output_path: Path
) -> None:
    lines = [
        "# Load Test Results",
        "",
        f"Target: `{url}`. Query mix drawn round-robin from `eval/dataset.jsonl` "
        "(lexical / semantic / confusable).",
        "",
        "## POST /api/analyze (full pipeline: sanitize -> guard -> retrieve -> "
        "rerank -> generate -> cite)",
        "",
        format_table(analyze_levels),
        "",
        "## GET /api/health (transport/API overhead only -- no retrieval or LLM call)",
        "",
        format_table(health_levels),
        "",
        "**Reading the error rate column:** the server's default rate limiter allows 30 "
        "requests / 60 s per client (`API_RATE_LIMIT_REQUESTS` / "
        "`API_RATE_LIMIT_WINDOW_SECONDS`), shared across every `/api/*` route including "
        "`/api/health`. This script is one client, so 429s at higher concurrency reflect "
        "that configured protection working as intended, not the pipeline failing -- see "
        "DECISIONS.md D23 and D26.",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Concurrent load test against /api/analyze and /api/health.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url", default="http://127.0.0.1:7860", help="Base URL of the running server."
    )
    parser.add_argument(
        "--users",
        type=int,
        nargs="+",
        default=_DEFAULT_USERS,
        help="Concurrency levels to test (default: 1 5 10 20 50).",
    )
    parser.add_argument(
        "--cooldown-seconds",
        type=float,
        default=65.0,
        help="Pause between the analyze sweep and the health sweep so the shared "
        "rate-limit budget clears first (0 to skip).",
    )
    parser.add_argument(
        "--output", default="load_test_results.md", help="Output Markdown file path."
    )
    args = parser.parse_args()

    questions = load_questions()
    question_cycle = cycle(questions)

    print(f"Target: {args.url}")
    print(f"Concurrency levels: {args.users}")

    analyze_levels = asyncio.run(
        run_sweep(args.url, "/api/analyze", "POST", args.users, question_cycle, "analyze")
    )

    if args.cooldown_seconds > 0:
        print(
            f"\nCooling down {args.cooldown_seconds:.0f}s so /api/health starts from a "
            "clean rate-limit budget..."
        )
        time.sleep(args.cooldown_seconds)

    health_levels = asyncio.run(
        run_sweep(args.url, "/api/health", "GET", args.users, question_cycle, "health")
    )

    output_path = Path(args.output)
    write_report(args.url, analyze_levels, health_levels, output_path)

    print(f"\nWrote {output_path}")


if __name__ == "__main__":
    main()
