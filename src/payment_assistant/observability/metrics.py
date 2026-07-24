"""Prometheus metrics: counters/histograms plus an optional HTTP exposition server.

Collection always happens — incrementing an in-memory counter costs microseconds — so
toggling ``METRICS_ENABLED`` never changes what the app measures, only whether Prometheus
can scrape it. This keeps ``/metrics`` genuinely optional (per-deployment) without the
rest of the code needing to branch on the flag.

SECURITY: every label used here is a fixed, low-cardinality category (a stage name, a
sanitization category like "[EMAIL]", a retriever strategy name, a status word) — never
raw request content. The exposition endpoint therefore cannot leak query text or PII by
construction; ``tests/security/test_pii_leak_scan.py`` verifies this holds.
"""

from __future__ import annotations

import logging

from prometheus_client import Counter, Histogram, start_http_server

from ..sanitization import Redaction

logger = logging.getLogger(__name__)

REQUEST_COUNT = Counter(
    "rag_requests_total", "Total answer requests, by outcome", ["status"]
)
STAGE_DURATION = Histogram(
    "rag_stage_duration_seconds", "Duration of each pipeline stage", ["stage"]
)
REDACTIONS = Counter(
    "rag_sanitization_redactions_total", "PII items masked, by category", ["category"]
)
RETRIEVER_STRATEGY = Counter(
    "rag_retriever_strategy_total", "Requests handled, by retriever strategy", ["strategy"]
)

_server_started = False


def start_metrics_server(port: int) -> None:
    """Start the Prometheus HTTP exposition server once (idempotent per process)."""

    global _server_started
    if _server_started:
        return
    start_http_server(port)
    _server_started = True
    logger.info("Metrics server listening", extra={"step": "metrics_server", "status": "ok"})


def record_redactions(redactions: list[Redaction]) -> None:
    """Record sanitization counts, one increment per masked category (never the values)."""

    for r in redactions:
        REDACTIONS.labels(category=r.label).inc(r.count)
