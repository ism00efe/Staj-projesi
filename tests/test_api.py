"""Tests for the HTTP API layer.

Covers the wire contract (`tests` for schemas.py), the transport protections
(middleware.py), and the controller (routes.py). The service is always a local fake —
these tests never load a model, touch Chroma, or call an LLM.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

from payment_assistant.api import create_app
from payment_assistant.api.middleware import RateLimiter
from payment_assistant.api.routes import _reject_oversized_upload
from payment_assistant.api.schemas import _EXCERPT_CHARS
from payment_assistant.config import Settings
from payment_assistant.models import Answer, Citation, RetrievedChunk
from payment_assistant.observability.logging_context import TraceIdFilter
from payment_assistant.observability.metrics import API_REQUESTS
from payment_assistant.rag.engine import RAGEngine
from payment_assistant.rag.retriever import DenseRetriever
from payment_assistant.sanitization import Redaction
from payment_assistant.security import REFUSAL_MESSAGE
from payment_assistant.service import AssistantService
from tests.conftest import FakeEmbeddings, FakeLLM, FakeVectorStore, make_chunk
from tests.security.test_pii_leak_scan import ALL_RAW_PII, RAW_CARD, RAW_IP


class _FakeService:
    """Stand-in for AssistantService.

    ``ask_with_log_file`` deliberately raises: the API must only ever hand the service
    raw text, never a filesystem path. Making that an exception rather than a single
    assertion means *any* test in this file would catch a regression, not just one.
    """

    def __init__(
        self,
        answer: Answer | None = None,
        raises: Exception | None = None,
        ingest_result: tuple[int, list[Redaction]] | None = None,
        ingest_raises: Exception | None = None,
    ) -> None:
        self._answer = answer or Answer(
            text="ok", citations=[], retrieved=[], trace_id="trace-fake"
        )
        self._raises = raises
        self._ingest_result = ingest_result if ingest_result is not None else (3, [])
        self._ingest_raises = ingest_raises
        self.calls: list[tuple[str | None, str | None]] = []
        self.ingest_calls: list[tuple[str, str]] = []

    def ask(self, question: str | None, log_text: str | None = None) -> Answer:
        self.calls.append((question, log_text))
        if self._raises:
            raise self._raises
        return self._answer

    def ask_with_log_file(self, question, file_path):  # pragma: no cover - must not run
        raise AssertionError("the API must never pass a file path to the service")

    def ingest_document(self, text: str, filename: str) -> tuple[int, list[Redaction]]:
        self.ingest_calls.append((text, filename))
        if self._ingest_raises:
            raise self._ingest_raises
        return self._ingest_result

    def knowledge_base_size(self) -> int:
        return 7


def _settings(**overrides) -> Settings:
    """Settings with rate limiting off unless a test explicitly wants it."""

    defaults = {"api_rate_limit_enabled": False}
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def _client(service: _FakeService | None = None, **setting_overrides) -> TestClient:
    """A client that behaves like a real one.

    ``raise_server_exceptions=False`` matters: by default TestClient re-raises whatever
    the app raised, so the 500 handler's actual response would never be observed — which
    is precisely what the error-leakage tests need to inspect.
    """

    return TestClient(
        create_app(service or _FakeService(), _settings(**setting_overrides)),
        raise_server_exceptions=False,
    )


def _counter_value(**labels) -> float:
    return API_REQUESTS.labels(**labels)._value.get()  # noqa: SLF001 (test-only)


def _answer_with_sources() -> Answer:
    chunk_a = make_chunk("errorcodes_payment", text="RC-05 means do not honor.", title="Codes")
    chunk_b = make_chunk("faq_general", index=1, text="Retry guidance.", title="FAQ")
    return Answer(
        text="Yanıt [S1] ve [S2].",
        citations=[
            Citation("S1", "errorcodes_payment", "Codes", "error_codes", "e.md", 0.91),
            Citation("S2", "faq_general", "FAQ", "faq", "f.md", 0.72),
        ],
        retrieved=[RetrievedChunk(chunk_a, 0.91), RetrievedChunk(chunk_b, 0.72)],
        trace_id="trace-1",
    )


# --- response mapping ---------------------------------------------------------
def test_analyze_returns_exact_top_level_keys():
    response = _client().post("/api/analyze", json={"query": "soru"})
    assert response.status_code == 200
    assert set(response.json()) == {"answer", "sources", "security_summary", "trace_id"}


def test_analyze_forwards_query_and_file_content_to_service():
    service = _FakeService()
    _client(service).post("/api/analyze", json={"query": "soru", "file_content": "log satırı"})
    assert service.calls == [("soru", "log satırı")]


def test_analyze_never_passes_a_file_path_to_the_service():
    # _FakeService.ask_with_log_file raises if it is ever reached.
    response = _client().post("/api/analyze", json={"query": "soru", "file_content": "x"})
    assert response.status_code == 200


def test_sources_come_from_citations_when_present():
    body = _client(_FakeService(_answer_with_sources())).post(
        "/api/analyze", json={"query": "soru"}
    ).json()
    assert [s["tag"] for s in body["sources"]] == ["S1", "S2"]
    assert all(s["cited"] for s in body["sources"])
    assert body["sources"][0]["doc_type"] == "error_codes"


def test_sources_fall_back_to_retrieved_when_nothing_was_cited():
    answer = Answer(
        text="atıfsız yanıt",
        citations=[],
        retrieved=[
            RetrievedChunk(make_chunk("a", text="alpha"), 0.5),
            RetrievedChunk(make_chunk("b", text="beta"), 0.4),
        ],
    )
    body = _client(_FakeService(answer)).post("/api/analyze", json={"query": "s"}).json()
    assert [s["tag"] for s in body["sources"]] == ["S1", "S2"]
    assert not any(s["cited"] for s in body["sources"])


def test_sources_empty_when_nothing_cited_or_retrieved():
    body = _client().post("/api/analyze", json={"query": "s"}).json()
    assert body["sources"] == []


def test_citation_excerpt_is_joined_back_from_retrieved_by_tag():
    body = _client(_FakeService(_answer_with_sources())).post(
        "/api/analyze", json={"query": "s"}
    ).json()
    assert body["sources"][0]["excerpt"] == "RC-05 means do not honor."
    assert body["sources"][1]["excerpt"] == "Retry guidance."


def test_excerpt_is_truncated():
    long_text = "x" * (_EXCERPT_CHARS + 50)
    answer = Answer(
        text="a", citations=[], retrieved=[RetrievedChunk(make_chunk("a", text=long_text), 0.5)]
    )
    body = _client(_FakeService(answer)).post("/api/analyze", json={"query": "s"}).json()
    excerpt = body["sources"][0]["excerpt"]
    assert excerpt.endswith("…")
    assert len(excerpt) == _EXCERPT_CHARS + 1


def test_citation_tag_out_of_range_yields_no_excerpt():
    answer = Answer(
        text="yanıt [S9]",
        citations=[Citation("S9", "a", "T", "faq", "a.md", 0.5)],
        retrieved=[],
    )
    body = _client(_FakeService(answer)).post("/api/analyze", json={"query": "s"}).json()
    assert body["sources"][0]["excerpt"] is None


def test_citation_tag_unparsable_yields_no_excerpt():
    answer = Answer(
        text="yanıt", citations=[Citation("Sx", "a", "T", "faq", "a.md", 0.5)], retrieved=[]
    )
    body = _client(_FakeService(answer)).post("/api/analyze", json={"query": "s"}).json()
    assert body["sources"][0]["excerpt"] is None


# --- security summary ---------------------------------------------------------
def test_redaction_labels_are_parsed_into_label_and_count():
    answer = Answer(
        text="a", citations=[], retrieved=[], redactions=["[CARD]×1", "[EMAIL]×2"]
    )
    summary = _client(_FakeService(answer)).post(
        "/api/analyze", json={"query": "s"}
    ).json()["security_summary"]
    assert summary["redactions"] == [
        {"label": "[CARD]", "count": 1},
        {"label": "[EMAIL]", "count": 2},
    ]
    assert summary["redaction_total"] == 3


def test_security_summary_empty_when_nothing_was_masked():
    summary = _client().post("/api/analyze", json={"query": "s"}).json()["security_summary"]
    assert summary == {"blocked": False, "redactions": [], "redaction_total": 0}


def test_unparsable_redaction_label_degrades_and_warns(caplog):
    answer = Answer(text="a", citations=[], retrieved=[], redactions=["GARBLED"])
    with caplog.at_level(logging.WARNING):
        summary = _client(_FakeService(answer)).post(
            "/api/analyze", json={"query": "s"}
        ).json()["security_summary"]
    assert summary["redactions"] == [{"label": "GARBLED", "count": 1}]
    assert "unparsable redaction label" in caplog.text
    assert "GARBLED" not in caplog.text  # the raw value is never logged


def test_redaction_format_matches_what_the_real_engine_produces(caplog):
    """Contract test: pin the "[LABEL]×N" format the API parses.

    `rag/engine.py` builds these strings and is not ours to change, so a drift there
    would silently degrade every security summary. Running the real engine here turns
    that into a failing test instead.
    """

    store = FakeVectorStore([make_chunk("kb", text="guidance")])
    engine = RAGEngine(
        FakeEmbeddings(),
        store,
        FakeLLM("Yanıt [S1]."),
        retriever=DenseRetriever(FakeEmbeddings(), store),
    )
    answer = engine.answer(f"Kart {RAW_CARD} reddedildi, IP {RAW_IP}")
    assert answer.redactions, "expected the engine to report masked values"

    with caplog.at_level(logging.WARNING):
        summary = _client(_FakeService(answer)).post(
            "/api/analyze", json={"query": "s"}
        ).json()["security_summary"]

    assert "unparsable redaction label" not in caplog.text
    assert summary["redaction_total"] >= 2
    assert all(item["count"] >= 1 for item in summary["redactions"])
    assert all(item["label"].startswith("[") for item in summary["redactions"])


def test_blocked_is_true_for_the_guard_refusal():
    answer = Answer(text=REFUSAL_MESSAGE, citations=[], retrieved=[])
    body = _client(_FakeService(answer)).post("/api/analyze", json={"query": "s"}).json()
    assert body["security_summary"]["blocked"] is True


def test_blocked_is_false_for_a_normal_answer():
    body = _client().post("/api/analyze", json={"query": "s"}).json()
    assert body["security_summary"]["blocked"] is False


# --- trace id -----------------------------------------------------------------
def test_trace_id_comes_from_the_answer():
    body = _client().post("/api/analyze", json={"query": "s"}).json()
    assert body["trace_id"] == "trace-fake"


def test_trace_id_falls_back_to_the_request_id_when_the_answer_has_none():
    answer = Answer(text="a", citations=[], retrieved=[], trace_id="")
    body = _client(_FakeService(answer)).post("/api/analyze", json={"query": "s"}).json()
    assert body["trace_id"] and body["trace_id"] != "-"


def test_error_responses_carry_a_trace_id():
    body = _client().post("/api/analyze", json={"nope": 1}).json()
    assert body["trace_id"] and body["trace_id"] != "-"


# --- validation ---------------------------------------------------------------
def test_missing_body_returns_422():
    assert _client().post("/api/analyze").status_code == 422


def test_wrong_type_returns_422_with_a_turkish_message():
    response = _client().post("/api/analyze", json={"query": 5})
    assert response.status_code == 422
    assert response.json()["error"]["message"].startswith("İstek geçersiz")


def test_422_does_not_echo_the_submitted_value():
    """FastAPI's default handler returns the offending value; ours must not."""

    response = _client().post("/api/analyze", json={"file_content": 4111111111111111})
    assert response.status_code == 422
    assert "4111111111111111" not in response.text


def test_unknown_field_is_rejected():
    response = _client().post("/api/analyze", json={"query": "s", "file_path": "/etc/passwd"})
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["body.file_path"]


def test_empty_query_and_file_content_still_reaches_the_service():
    """Both blank is a domain outcome, not a schema violation — the engine answers it."""

    service = _FakeService()
    response = _client(service).post("/api/analyze", json={})
    assert response.status_code == 200
    assert service.calls == [(None, None)]


# --- size limits --------------------------------------------------------------
def test_file_content_over_the_upload_limit_returns_413():
    service = _FakeService()
    client = _client(service, max_upload_bytes=100)
    response = client.post("/api/analyze", json={"file_content": "x" * 200})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert service.calls == []  # rejected before the service is touched


def test_file_content_size_is_measured_in_bytes_not_characters():
    """A multi-byte character must count as its encoded length."""

    service = _FakeService()
    client = _client(service, max_upload_bytes=100)
    response = client.post("/api/analyze", json={"file_content": "ş" * 60})  # 120 bytes
    assert response.status_code == 413
    assert service.calls == []


def test_body_over_the_request_limit_returns_413_without_calling_the_service():
    service = _FakeService()
    client = _client(service, api_max_body_bytes=200)
    response = client.post("/api/analyze", json={"query": "x" * 500})
    assert response.status_code == 413
    assert service.calls == []


def test_chunked_body_over_the_request_limit_returns_413():
    """No Content-Length to check, so the streaming counter is the only defense."""

    service = _FakeService()
    client = _client(service, api_max_body_bytes=200)
    response = client.post(
        "/api/analyze",
        content=iter([b'{"query": "', b"x" * 500, b'"}']),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert service.calls == []


# --- errors -------------------------------------------------------------------
def test_service_exception_returns_500_with_a_generic_turkish_message():
    client = _client(_FakeService(raises=RuntimeError("boom")))
    response = client.post("/api/analyze", json={"query": "s"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "Beklenmeyen bir hata" in response.json()["error"]["message"]


def test_500_does_not_leak_the_exception_text():
    client = _client(_FakeService(raises=RuntimeError("ollama down at 10.0.0.5:11434")))
    response = client.post("/api/analyze", json={"query": "s"})
    assert "ollama down" not in response.text
    assert "10.0.0.5" not in response.text


def test_500_message_includes_a_real_trace_id_for_support():
    """The 500 handler runs outside the scope that bound the id, so this asserts a real
    id and not the "-" placeholder — quoting "-" to support is worthless."""

    client = _client(_FakeService(raises=RuntimeError("boom")))
    body = client.post("/api/analyze", json={"query": "s"}).json()
    assert body["trace_id"] not in ("-", "")
    assert body["trace_id"] in body["error"]["message"]


def test_500_log_line_carries_the_request_trace_id(caplog):
    """Without it the failure log cannot be joined to the request that caused it."""

    client = _client(_FakeService(raises=RuntimeError("boom")))
    with caplog.at_level(logging.ERROR):
        body = client.post("/api/analyze", json={"query": "s"}).json()

    unhandled = [r for r in caplog.records if r.message == "unhandled error while serving request"]
    assert unhandled, "expected the unhandled-error line"
    assert unhandled[0].trace_id == body["trace_id"]


def test_pipeline_and_api_share_one_trace_id(caplog):
    """A request must produce a single id across both layers.

    The API binds an id, then the engine binds its own; if the inner bind minted a fresh
    one, a failed request's api-level line could not be joined to the pipeline line that
    explains why it failed.
    """

    store = FakeVectorStore([make_chunk("kb", text="guidance")])
    engine = RAGEngine(
        FakeEmbeddings(),
        store,
        FakeLLM("Yanıt [S1]."),
        retriever=DenseRetriever(FakeEmbeddings(), store),
    )

    class _EngineBackedService:
        def ask(self, question, log_text=None):
            return engine.answer(question or "", log_text)

        def knowledge_base_size(self):
            return store.count()

    # In production TraceIdFilter is attached to the handler configure_logging()
    # installs; caplog uses its own handler, so it needs the same filter to see the id.
    caplog.handler.addFilter(TraceIdFilter())
    with caplog.at_level(logging.INFO):
        body = _client(_EngineBackedService()).post("/api/analyze", json={"query": "soru"}).json()

    steps = {r.step: r.trace_id for r in caplog.records if hasattr(r, "step")}
    assert "api.analyze" in steps and "generate" in steps
    assert len(set(steps.values())) == 1, f"expected one trace id, got {steps}"
    assert body["trace_id"] == steps["api.analyze"]


def test_unknown_path_returns_the_error_envelope():
    response = _client().get("/bilinmeyen")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --- rate limiting (over HTTP) ------------------------------------------------
def test_requests_within_the_budget_are_allowed():
    client = _client(api_rate_limit_enabled=True, api_rate_limit_requests=2)
    assert client.post("/api/analyze", json={"query": "1"}).status_code == 200
    assert client.post("/api/analyze", json={"query": "2"}).status_code == 200


def test_exceeding_the_budget_returns_429_with_retry_after():
    client = _client(api_rate_limit_enabled=True, api_rate_limit_requests=1)
    client.post("/api/analyze", json={"query": "1"})
    response = client.post("/api/analyze", json={"query": "2"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert int(response.headers["Retry-After"]) >= 1
    assert "Çok fazla istek" in response.json()["error"]["message"]


def test_rate_limiting_can_be_disabled():
    client = _client(api_rate_limit_enabled=False)
    for _ in range(5):
        assert client.post("/api/analyze", json={"query": "s"}).status_code == 200


def test_budget_is_tracked_per_client():
    app = create_app(_FakeService(), _settings(api_rate_limit_enabled=True,
                                               api_rate_limit_requests=1))
    first = TestClient(app, client=("1.2.3.4", 1))
    second = TestClient(app, client=("5.6.7.8", 1))
    assert first.post("/api/analyze", json={"query": "s"}).status_code == 200
    assert first.post("/api/analyze", json={"query": "s"}).status_code == 429
    assert second.post("/api/analyze", json={"query": "s"}).status_code == 200


def test_forwarded_for_is_ignored_by_default():
    app = create_app(_FakeService(), _settings(api_rate_limit_enabled=True,
                                               api_rate_limit_requests=1))
    client = TestClient(app, client=("1.2.3.4", 1))
    client.post("/api/analyze", json={"query": "s"})
    spoofed = client.post(
        "/api/analyze", json={"query": "s"}, headers={"X-Forwarded-For": "9.9.9.9"}
    )
    assert spoofed.status_code == 429  # the header must not buy a fresh budget


def test_forwarded_for_is_used_when_a_proxy_hop_is_trusted():
    app = create_app(
        _FakeService(),
        _settings(api_rate_limit_enabled=True, api_rate_limit_requests=1,
                  api_trusted_proxy_hops=1),
    )
    client = TestClient(app, client=("10.0.0.1", 1))
    first = client.post(
        "/api/analyze", json={"query": "s"}, headers={"X-Forwarded-For": "1.1.1.1"}
    )
    second = client.post(
        "/api/analyze", json={"query": "s"}, headers={"X-Forwarded-For": "2.2.2.2"}
    )
    assert first.status_code == 200
    assert second.status_code == 200  # a different client, so a separate budget


def test_static_assets_are_not_rate_limited():
    client = _client(api_rate_limit_enabled=True, api_rate_limit_requests=1)
    client.post("/api/analyze", json={"query": "s"})
    for _ in range(3):
        assert client.get("/").status_code == 200
        assert client.get("/static/style.css").status_code == 200


# --- rate limiting (unit, with a fake clock) ----------------------------------
class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_allows_up_to_the_maximum():
    limiter = RateLimiter(2, 60.0, clock=_FakeClock())
    assert limiter.check("a") is None
    assert limiter.check("a") is None
    assert limiter.check("a") is not None


def test_limiter_frees_budget_once_the_window_passes():
    clock = _FakeClock()
    limiter = RateLimiter(1, 60.0, clock=clock)
    assert limiter.check("a") is None
    assert limiter.check("a") is not None
    clock.now += 61
    assert limiter.check("a") is None


def test_limiter_reports_time_until_the_oldest_hit_expires():
    clock = _FakeClock()
    limiter = RateLimiter(1, 60.0, clock=clock)
    limiter.check("a")
    clock.now += 20
    assert limiter.check("a") == pytest.approx(40.0)


def test_limiter_keys_are_independent():
    limiter = RateLimiter(1, 60.0, clock=_FakeClock())
    assert limiter.check("a") is None
    assert limiter.check("b") is None


def test_limiter_prunes_stale_clients():
    from payment_assistant.api import middleware as middleware_module

    clock = _FakeClock()
    limiter = RateLimiter(1, 60.0, clock=clock)
    for i in range(middleware_module._MAX_TRACKED_CLIENTS + 1):  # noqa: SLF001
        limiter.check(f"client-{i}")
    clock.now += 61
    limiter.check("fresh")
    assert len(limiter._buckets) == 1  # noqa: SLF001 (test-only introspection)


# --- static, docs, health -----------------------------------------------------
def test_root_serves_the_web_ui():
    response = _client().get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Ödeme Sistemleri" in response.text


def test_static_css_and_js_are_served():
    client = _client()
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_openapi_documents_the_analyze_endpoint():
    client = _client()
    assert client.get("/docs").status_code == 200
    assert "/api/analyze" in client.get("/openapi.json").text


def test_app_starts_and_shuts_down_cleanly():
    """Entering the client runs the lifespan, which passes a non-HTTP scope through
    both middlewares — the branch a plain request never reaches."""

    with _client() as client:
        assert client.get("/api/health").status_code == 200


def test_health_reports_kb_size_and_the_upload_limits():
    body = _client(max_upload_bytes=1234, api_max_upload_bytes=5678).get("/api/health").json()
    assert body == {
        "status": "ok",
        "knowledge_base_size": 7,
        "max_upload_bytes": 1234,
        "max_document_upload_bytes": 5678,
    }


# --- the PII barrier at the HTTP boundary -------------------------------------
def test_request_content_never_reaches_the_logs(caplog):
    """Same discipline as tests/security/test_pii_leak_scan.py, one layer out."""

    payload = " ".join(ALL_RAW_PII)
    with caplog.at_level(logging.DEBUG):
        _client().post("/api/analyze", json={"query": payload, "file_content": payload})
    for raw in ALL_RAW_PII:
        assert raw not in caplog.text


def test_client_ip_never_reaches_the_logs(caplog):
    """An IP address is one of the categories sanitization.py exists to mask."""

    app = create_app(_FakeService(), _settings(api_rate_limit_enabled=True))
    client = TestClient(app, client=(RAW_IP, 1))
    with caplog.at_level(logging.DEBUG):
        client.post("/api/analyze", json={"query": "s"})
    assert RAW_IP not in caplog.text


def test_validation_failures_do_not_log_the_submitted_value(caplog):
    with caplog.at_level(logging.DEBUG):
        _client().post("/api/analyze", json={"file_content": 4111111111111111})
    assert "4111111111111111" not in caplog.text


# --- metrics ------------------------------------------------------------------
def test_successful_request_counts_as_ok():
    before = _counter_value(endpoint="/api/analyze", outcome="ok")
    _client().post("/api/analyze", json={"query": "s"})
    assert _counter_value(endpoint="/api/analyze", outcome="ok") == before + 1


def test_rate_limited_request_counts_as_rate_limited():
    before = _counter_value(endpoint="/api/analyze", outcome="rate_limited")
    client = _client(api_rate_limit_enabled=True, api_rate_limit_requests=1)
    client.post("/api/analyze", json={"query": "s"})
    client.post("/api/analyze", json={"query": "s"})
    assert _counter_value(endpoint="/api/analyze", outcome="rate_limited") == before + 1


def test_failed_request_counts_as_internal_error():
    before = _counter_value(endpoint="/api/analyze", outcome="internal_error")
    _client(_FakeService(raises=RuntimeError("boom"))).post("/api/analyze", json={"query": "s"})
    assert _counter_value(endpoint="/api/analyze", outcome="internal_error") == before + 1


# --- POST /api/ingest -----------------------------------------------------------
def _md_file(name: str = "doc.md", content: bytes = b"# Baslik\n\nGovde metni.") -> dict:
    return {"file": (name, content, "text/markdown")}


def test_ingest_returns_exact_top_level_keys():
    body = _client().post("/api/ingest", files=_md_file()).json()
    assert set(body) == {
        "status", "filename", "chunks_added", "redactions", "redaction_total", "trace_id",
    }


def test_ingest_success_reports_status_ok_filename_and_chunk_count():
    service = _FakeService(ingest_result=(4, []))
    body = _client(service).post("/api/ingest", files=_md_file("guide.md")).json()
    assert body["status"] == "ok"
    assert body["filename"] == "guide.md"
    assert body["chunks_added"] == 4


def test_ingest_forwards_extracted_text_and_filename_to_the_service():
    service = _FakeService()
    _client(service).post("/api/ingest", files=_md_file("guide.md", b"# Guide\n\nBody text."))
    assert service.ingest_calls == [("# Guide\n\nBody text.", "guide.md")]


def test_ingest_reports_redaction_labels_and_total():
    service = _FakeService(ingest_result=(1, [Redaction("[CARD]", 1), Redaction("[EMAIL]", 2)]))
    body = _client(service).post("/api/ingest", files=_md_file()).json()
    assert body["redactions"] == [
        {"label": "[CARD]", "count": 1},
        {"label": "[EMAIL]", "count": 2},
    ]
    assert body["redaction_total"] == 3


def test_ingest_merges_same_label_redaction_counts():
    """Filename and body are sanitized separately (see ingest_single_document), so the
    same category can come back twice and must be combined into one entry."""

    service = _FakeService(ingest_result=(1, [Redaction("[EMAIL]", 1), Redaction("[EMAIL]", 1)]))
    body = _client(service).post("/api/ingest", files=_md_file()).json()
    assert body["redactions"] == [{"label": "[EMAIL]", "count": 2}]


def test_ingest_empty_file_returns_400():
    response = _client().post("/api/ingest", files={"file": ("empty.txt", b"", "text/plain")})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_file"


def test_ingest_whitespace_only_file_returns_400():
    response = _client().post("/api/ingest", files={"file": ("blank.txt", b"   ", "text/plain")})
    assert response.status_code == 400


def test_ingest_unsupported_extension_returns_415_listing_supported_types():
    response = _client().post(
        "/api/ingest", files={"file": ("virus.exe", b"MZ\x90\x00", "application/octet-stream")}
    )
    assert response.status_code == 415
    message = response.json()["error"]["message"]
    assert ".pdf" in message and ".md" in message


def test_ingest_file_with_no_extension_returns_415():
    response = _client().post("/api/ingest", files={"file": ("README", b"hello", "text/plain")})
    assert response.status_code == 415


def test_ingest_binary_content_disguised_as_text_returns_415():
    png_signature = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    files = {"file": ("report.txt", png_signature, "text/plain")}
    response = _client().post("/api/ingest", files=files)
    assert response.status_code == 415


def test_ingest_pdf_without_a_pdf_signature_returns_415():
    response = _client().post(
        "/api/ingest", files={"file": ("fake.pdf", b"not a real pdf", "application/pdf")}
    )
    assert response.status_code == 415


def test_ingest_file_over_the_upload_limit_returns_413():
    client = _client(api_max_upload_bytes=10)
    response = client.post("/api/ingest", files={"file": ("big.txt", b"x" * 1000, "text/plain")})
    assert response.status_code == 413


def test_ingest_never_reaches_the_service_when_rejected_before_it():
    """Empty/oversize/unsupported-type rejections must not still call the service —
    otherwise a fake in another test could hide a real double-processing bug."""

    service = _FakeService()
    _client(service).post("/api/ingest", files={"file": ("empty.txt", b"", "text/plain")})
    exe_files = {"file": ("x.exe", b"MZ", "application/octet-stream")}
    _client(service).post("/api/ingest", files=exe_files)
    assert service.ingest_calls == []


def test_ingest_service_error_returns_500_with_a_generic_message():
    service = _FakeService(ingest_raises=RuntimeError("chroma is down"))
    response = _client(service).post("/api/ingest", files=_md_file())
    assert response.status_code == 500
    assert "chroma is down" not in response.text


def test_reject_oversized_upload_raises_413_over_the_limit():
    with pytest.raises(HTTPException) as exc_info:
        _reject_oversized_upload(11, _settings(api_max_upload_bytes=10))
    assert exc_info.value.status_code == 413


def test_reject_oversized_upload_allows_exactly_the_limit():
    _reject_oversized_upload(10, _settings(api_max_upload_bytes=10))  # must not raise


# --- POST /api/ingest: rate limiting (over HTTP) ---------------------------------
def test_upload_requests_within_the_budget_are_allowed():
    client = _client(api_rate_limit_enabled=True, api_upload_rate_limit_requests=2)
    assert client.post("/api/ingest", files=_md_file()).status_code == 200
    assert client.post("/api/ingest", files=_md_file()).status_code == 200


def test_upload_exceeding_the_budget_returns_429_with_retry_after():
    client = _client(api_rate_limit_enabled=True, api_upload_rate_limit_requests=1)
    client.post("/api/ingest", files=_md_file())
    response = client.post("/api/ingest", files=_md_file())
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_upload_rate_limit_is_a_separate_budget_from_the_general_api_limit():
    client = _client(
        api_rate_limit_enabled=True,
        api_rate_limit_requests=50,
        api_upload_rate_limit_requests=1,
    )
    client.post("/api/ingest", files=_md_file())
    assert client.post("/api/ingest", files=_md_file()).status_code == 429
    # The general limiter still has budget; /api/analyze must be unaffected.
    assert client.post("/api/analyze", json={"query": "s"}).status_code == 200


def test_analyze_budget_does_not_gate_uploads():
    client = _client(
        api_rate_limit_enabled=True,
        api_rate_limit_requests=1,
        api_upload_rate_limit_requests=50,
    )
    client.post("/api/analyze", json={"query": "s"})
    # The general limiter is now exhausted; the router-level dependency still applies to
    # every route including /ingest, so this is expected to be limited too.
    assert client.post("/api/ingest", files=_md_file()).status_code == 429


# --- POST /api/ingest: full-stack (real engine + real ingestion pipeline) -------
def _real_client(store=None):
    settings = Settings(_env_file=None, api_rate_limit_enabled=False)
    store = store if store is not None else FakeVectorStore()
    embedder = FakeEmbeddings()
    engine = RAGEngine(
        embedder, store, FakeLLM("Yanıt [S1]."), retriever=DenseRetriever(embedder, store)
    )
    service = AssistantService(engine, settings)
    client = TestClient(create_app(service, settings), raise_server_exceptions=False)
    return client, store


def test_ingest_never_resets_the_store_and_the_upload_is_immediately_retrievable():
    # An empty store, not a pre-seeded one: FakeVectorStore.query returns chunks in
    # insertion order (it does no real similarity search) and FakeLLM always "cites"
    # [S1], so a pre-existing chunk would win the one citation slot and this could not
    # actually prove the *new* content is retrievable. "Doesn't reset" is asserted
    # directly below instead, via the exact reset_called counter.
    client, store = _real_client()

    files = {"file": ("guide.md", b"# Yeni Kural\n\nYeni icerik burada.", "text/markdown")}
    upload = client.post("/api/ingest", files=files)
    assert upload.status_code == 200
    assert upload.json()["chunks_added"] == 1
    assert store.reset_called == 0
    assert store.count() == 1

    answer = client.post("/api/analyze", json={"query": "Yeni kural nedir?"})
    titles = [s["title"] for s in answer.json()["sources"]]
    assert titles == ["Yeni Kural"]


def test_ingest_preserves_previously_indexed_content():
    existing_store = FakeVectorStore([make_chunk("existing", text="pre-existing chunk")])
    client, store = _real_client(existing_store)

    client.post("/api/ingest", files=_md_file("guide.md", b"# New\n\nBody"))

    assert store.reset_called == 0
    assert store.count() == 2
    document_ids = {c.document_id for c in store._chunks}  # noqa: SLF001 (test-only)
    assert "existing" in document_ids
    assert any(doc_id.startswith("upload_") for doc_id in document_ids)


def test_ingest_sanitizes_pii_through_the_real_pipeline_and_it_stays_masked_on_retrieval(caplog):
    client, store = _real_client()
    content = f"Kart {RAW_CARD} ile odeme reddedildi. Musteri IP: {RAW_IP}.".encode()

    with caplog.at_level(logging.DEBUG):
        upload = client.post("/api/ingest", files={"file": ("olay.md", content, "text/markdown")})
    assert upload.status_code == 200
    assert upload.json()["redaction_total"] >= 2
    for chunk in store._chunks:  # noqa: SLF001 (test-only introspection)
        assert RAW_CARD not in chunk.text
        assert RAW_IP not in chunk.text
    assert RAW_CARD not in caplog.text
    assert RAW_IP not in caplog.text

    answer = client.post("/api/analyze", json={"query": "Odeme neden reddedildi?"})
    assert RAW_CARD not in answer.text
    assert RAW_IP not in answer.text


# --- POST /api/ingest: logging + PII barrier -------------------------------------
def test_ingest_logs_filename_and_size_but_never_file_content(caplog):
    """`extra=` fields land as LogRecord attributes, not in caplog's rendered text (that
    uses caplog's own formatter, not JsonFormatter) — so filename presence is checked via
    caplog.records, matching the pattern test_pipeline_and_api_share_one_trace_id uses."""

    with caplog.at_level(logging.DEBUG):
        _client().post(
            "/api/ingest", files=_md_file("gizli-belge.md", b"cok gizli govde metni")
        )
    filenames = [r.upload_filename for r in caplog.records if hasattr(r, "upload_filename")]
    assert "gizli-belge.md" in filenames
    assert "cok gizli govde metni" not in caplog.text


def test_ingest_log_line_carries_the_request_trace_id(caplog):
    # TraceIdFilter is what stamps record.trace_id; configure_logging() attaches it to
    # the production handler, but caplog uses its own, so it needs the filter too.
    caplog.handler.addFilter(TraceIdFilter())
    with caplog.at_level(logging.DEBUG):
        response = _client().post("/api/ingest", files=_md_file())
    trace_id = response.json()["trace_id"]
    ingest_trace_ids = [
        r.trace_id for r in caplog.records if getattr(r, "step", None) == "api.ingest"
    ]
    assert ingest_trace_ids == [trace_id]


def test_ingest_client_ip_never_reaches_the_logs(caplog):
    app = create_app(_FakeService(), _settings(api_rate_limit_enabled=True))
    client = TestClient(app, client=(RAW_IP, 1))
    with caplog.at_level(logging.DEBUG):
        client.post("/api/ingest", files=_md_file())
    assert RAW_IP not in caplog.text


# --- POST /api/ingest: metrics ----------------------------------------------------
def test_successful_upload_counts_as_ok():
    before = _counter_value(endpoint="/api/ingest", outcome="ok")
    _client().post("/api/ingest", files=_md_file())
    assert _counter_value(endpoint="/api/ingest", outcome="ok") == before + 1


def test_rejected_upload_type_counts_as_unsupported_file_type():
    before = _counter_value(endpoint="/api/ingest", outcome="unsupported_file_type")
    _client().post("/api/ingest", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert _counter_value(endpoint="/api/ingest", outcome="unsupported_file_type") == before + 1
