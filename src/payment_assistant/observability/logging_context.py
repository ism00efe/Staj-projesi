"""Structured logging primitives: trace-id propagation and JSON formatting.

A single ``trace_id`` is generated once per request and must show up on every log line
emitted while that request is in flight — including lines from nested layers (retriever,
reranker, LLM provider) that have no idea a "request" exists. Rather than threading a
``trace_id`` parameter through every function signature, we bind it to a ``ContextVar``
for the duration of the request and inject it into log records via a ``logging.Filter``
attached to the handler. Every layer keeps its existing signature; every log line still
gets the id.

SECURITY: log messages and the structured ``extra`` fields used here must never carry raw
user-supplied text (queries, log content). Only fixed step names, durations, counts, and
low-cardinality category labels are logged — verified by
``tests/security/test_pii_leak_scan.py``.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterator

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")

# Fixed, known set of structured fields a log record may carry. Keeping this explicit
# (rather than dumping the whole record.__dict__) means the JSON schema is stable and
# nothing accidental — like a raw query string passed via `extra=` by mistake — leaks in.
_EXTRA_FIELDS = (
    "step",
    "duration_ms",
    "status",
    "chunk_count",
    "redaction_count",
    "citation_count",
    "candidate_count",
    "result_count",
    "strategy",
    "reason",
    "token_count",
    "prompt_token_count",
    "error",
)


def new_trace_id() -> str:
    """Generate a short, sufficiently-unique trace id."""

    return uuid.uuid4().hex[:12]


def get_trace_id() -> str:
    """Return the trace id bound to the current context, or ``"-"`` if none."""

    return _trace_id_var.get()


@contextmanager
def bind_trace_id(trace_id: str | None = None) -> Iterator[str]:
    """Bind ``trace_id`` (or a freshly generated one) for the duration of the block.

    Every log record emitted anywhere during the block — including from nested calls
    that never see ``trace_id`` as a parameter — picks it up via :class:`TraceIdFilter`.
    """

    tid = trace_id or new_trace_id()
    token = _trace_id_var.set(tid)
    try:
        yield tid
    finally:
        _trace_id_var.reset(token)


class TraceIdFilter(logging.Filter):
    """Attach the current trace id to every record that doesn't already have one.

    Attached to a *handler* (not a logger) so it applies to every record reaching that
    handler, including from third-party libraries — guaranteeing ``%(trace_id)s`` /
    the JSON formatter never hits a missing attribute.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = get_trace_id()
        return True


class JsonFormatter(logging.Formatter):
    """Render a log record as a single JSON line.

    Only the fixed base fields plus any of :data:`_EXTRA_FIELDS` present on the record
    are included — see the module docstring for why that allowlist matters.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "-"),
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class _StepRecorder:
    """Mutable bag a ``log_step`` caller uses to attach fields discovered mid-block."""

    def __init__(self, initial: dict[str, object]) -> None:
        self.extra: dict[str, object] = dict(initial)

    def set(self, **fields: object) -> None:
        self.extra.update(fields)


@contextmanager
def log_step(
    step: str, logger: logging.Logger | None = None, **initial_extra: object
) -> Iterator[_StepRecorder]:
    """Time a pipeline step and log its outcome as a single structured record.

    Usage::

        with log_step("retrieve") as rec:
            retrieved = engine.retrieve(query)
            rec.set(chunk_count=len(retrieved))

    On success logs at INFO with ``status="ok"``; on exception logs at ERROR with
    ``status="error"`` and the exception message, then re-raises (never swallows).
    """

    log = logger or logging.getLogger("payment_assistant.observability")
    recorder = _StepRecorder(initial_extra)
    start = time.perf_counter()
    try:
        yield recorder
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        log.error(
            "step failed: %s",
            step,
            extra={
                "step": step,
                "duration_ms": duration_ms,
                "status": "error",
                "error": str(exc),
                **recorder.extra,
            },
        )
        raise
    else:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        log.info(
            "step completed: %s",
            step,
            extra={
                "step": step,
                "duration_ms": duration_ms,
                "status": "ok",
                **recorder.extra,
            },
        )
