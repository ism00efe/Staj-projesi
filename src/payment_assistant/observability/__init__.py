"""Observability: structured logging with trace-id propagation + Prometheus metrics.

``instrumented_step`` is the one thing most callers need: it times a pipeline stage,
logs a structured record for it (via :mod:`.logging_context`), and records the same
duration in the Prometheus histogram (via :mod:`.metrics`) — so instrumenting a stage is
a single ``with`` block instead of two.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from .logging_context import (
    JsonFormatter,
    TraceIdFilter,
    bind_trace_id,
    get_trace_id,
    has_trace_id,
    log_step,
    new_trace_id,
)
from .metrics import (
    API_REQUEST_DURATION,
    API_REQUESTS,
    REDACTIONS,
    REQUEST_COUNT,
    RETRIEVER_STRATEGY,
    STAGE_DURATION,
    record_redactions,
    start_metrics_server,
)


@contextmanager
def instrumented_step(step: str, logger: logging.Logger | None = None, **initial_extra: object):
    """Time + log + record-a-metric for one named pipeline stage.

    Usage::

        with instrumented_step("retrieve") as rec:
            retrieved = engine.retrieve(query)
            rec.set(chunk_count=len(retrieved))
    """

    with STAGE_DURATION.labels(stage=step).time():
        with log_step(step, logger, **initial_extra) as recorder:
            yield recorder


__all__ = [
    "JsonFormatter",
    "TraceIdFilter",
    "bind_trace_id",
    "get_trace_id",
    "has_trace_id",
    "new_trace_id",
    "log_step",
    "instrumented_step",
    "REQUEST_COUNT",
    "STAGE_DURATION",
    "REDACTIONS",
    "RETRIEVER_STRATEGY",
    "API_REQUESTS",
    "API_REQUEST_DURATION",
    "record_redactions",
    "start_metrics_server",
]
