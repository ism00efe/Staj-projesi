"""Tests for Prometheus metrics collection and the (mocked) exposition server."""

from __future__ import annotations

import payment_assistant.observability.metrics as metrics_module
from payment_assistant.observability.metrics import (
    REDACTIONS,
    REQUEST_COUNT,
    RETRIEVER_STRATEGY,
    STAGE_DURATION,
    record_redactions,
    start_metrics_server,
)
from payment_assistant.sanitization import Redaction


def _counter_value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()  # noqa: SLF001 (test-only introspection)


def _histogram_count(hist, **labels) -> float:
    """Read a Histogram's observation count via the public `.collect()` API."""

    for metric in hist.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count") and sample.labels == labels:
                return sample.value
    return 0.0


# --- counters/histograms are wired correctly --------------------------------
def test_request_count_increments_by_status():
    before = _counter_value(REQUEST_COUNT, status="ok")
    REQUEST_COUNT.labels(status="ok").inc()
    assert _counter_value(REQUEST_COUNT, status="ok") == before + 1


def test_stage_duration_observes():
    before = _histogram_count(STAGE_DURATION, stage="sanitize")
    STAGE_DURATION.labels(stage="sanitize").observe(0.01)
    assert _histogram_count(STAGE_DURATION, stage="sanitize") == before + 1


def test_retriever_strategy_counter():
    before = _counter_value(RETRIEVER_STRATEGY, strategy="hybrid")
    RETRIEVER_STRATEGY.labels(strategy="hybrid").inc()
    assert _counter_value(RETRIEVER_STRATEGY, strategy="hybrid") == before + 1


# --- record_redactions --------------------------------------------------------
def test_record_redactions_increments_by_category():
    before = _counter_value(REDACTIONS, category="[EMAIL]")
    record_redactions([Redaction("[EMAIL]", 2), Redaction("[CARD]", 1)])
    assert _counter_value(REDACTIONS, category="[EMAIL]") == before + 2


def test_record_redactions_empty_list_is_noop():
    before = _counter_value(REDACTIONS, category="[IP]")
    record_redactions([])
    assert _counter_value(REDACTIONS, category="[IP]") == before


# --- start_metrics_server (no real socket bound) ------------------------------
def test_start_metrics_server_calls_prometheus_start_http_server(monkeypatch):
    monkeypatch.setattr(metrics_module, "_server_started", False)
    calls = []
    monkeypatch.setattr(metrics_module, "start_http_server", lambda port: calls.append(port))

    start_metrics_server(9999)
    assert calls == [9999]


def test_start_metrics_server_is_idempotent(monkeypatch):
    monkeypatch.setattr(metrics_module, "_server_started", False)
    calls = []
    monkeypatch.setattr(metrics_module, "start_http_server", lambda port: calls.append(port))

    start_metrics_server(9999)
    start_metrics_server(9999)  # second call must be a no-op
    assert calls == [9999]
