"""Tests for the application service (facade + composition root)."""

from __future__ import annotations

import payment_assistant.service as service_module
from payment_assistant.config import Settings
from payment_assistant.models import Answer
from payment_assistant.rag.retriever import DenseRetriever, HybridRetriever
from payment_assistant.service import AssistantService, build_retriever, build_service
from tests.conftest import FakeEmbeddings, FakeLLM, FakeVectorStore, make_chunk


class FakeEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def answer(self, question: str, log_text: str | None = None) -> Answer:
        self.calls.append((question, log_text))
        return Answer(text="ok", citations=[], retrieved=[])

    def corpus_size(self) -> int:
        return 7


def test_ask_delegates_to_engine():
    engine = FakeEngine()
    svc = AssistantService(engine, Settings(_env_file=None))
    svc.ask("question", "log")
    assert engine.calls == [("question", "log")]


def test_ask_with_log_file_reads_file(tmp_path):
    log = tmp_path / "log.json"
    log.write_text('{"error_code": "PAY-1001"}', encoding="utf-8")
    engine = FakeEngine()
    svc = AssistantService(engine, Settings(_env_file=None))
    svc.ask_with_log_file("q", str(log))
    question, log_text = engine.calls[0]
    assert question == "q" and "PAY-1001" in log_text


def test_ask_with_log_file_none_path():
    engine = FakeEngine()
    svc = AssistantService(engine, Settings(_env_file=None))
    svc.ask_with_log_file("q", None)
    assert engine.calls == [("q", None)]


def test_ask_with_log_file_rejects_oversized_upload(tmp_path):
    """SECURITY: a file above MAX_UPLOAD_BYTES must be refused before it is ever read
    into memory, and must never reach the engine (avoids a trivial DoS vector)."""
    log = tmp_path / "huge.json"
    log.write_text("x" * 200, encoding="utf-8")
    engine = FakeEngine()
    svc = AssistantService(engine, Settings(_env_file=None, max_upload_bytes=100))

    answer = svc.ask_with_log_file("q", str(log))

    assert engine.calls == []  # never reached the engine
    assert "büyük" in answer.text.lower()
    assert answer.trace_id  # rejection is still traceable


def test_ask_with_log_file_accepts_upload_within_limit(tmp_path):
    log = tmp_path / "small.json"
    log.write_text('{"error_code": "PAY-1001"}', encoding="utf-8")
    engine = FakeEngine()
    svc = AssistantService(engine, Settings(_env_file=None, max_upload_bytes=10_000))

    svc.ask_with_log_file("q", str(log))
    assert len(engine.calls) == 1


def test_knowledge_base_size_delegates():
    svc = AssistantService(FakeEngine(), Settings(_env_file=None))
    assert svc.knowledge_base_size() == 7


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_build_retriever_dense_only():
    retriever = build_retriever(
        _settings(), FakeEmbeddings(), FakeVectorStore(), hybrid=False, rerank=False
    )
    assert isinstance(retriever, DenseRetriever)


def test_build_retriever_hybrid(monkeypatch, tmp_path):
    (tmp_path / "faq_a.md").write_text("# A\n\nidempotency key usage", encoding="utf-8")
    retriever = build_retriever(
        _settings(corpus_dir=str(tmp_path)),
        FakeEmbeddings(), FakeVectorStore(), hybrid=True, rerank=False,
    )
    assert isinstance(retriever, HybridRetriever)
    assert retriever._sparse is not None  # noqa: SLF001
    assert retriever._reranker is None  # noqa: SLF001


def test_build_retriever_with_rerank(tmp_path):
    (tmp_path / "faq_a.md").write_text("# A\n\nbody", encoding="utf-8")
    retriever = build_retriever(
        _settings(corpus_dir=str(tmp_path)),
        FakeEmbeddings(), FakeVectorStore(), hybrid=True, rerank=True,
    )
    assert retriever._reranker is not None  # noqa: SLF001


def test_build_retriever_rerank_without_hybrid():
    """Re-ranking can be enabled on its own: dense candidates, no sparse fusion."""
    retriever = build_retriever(
        _settings(), FakeEmbeddings(), FakeVectorStore(), hybrid=False, rerank=True
    )
    assert isinstance(retriever, HybridRetriever)
    assert retriever._sparse is None  # noqa: SLF001
    assert retriever._reranker is not None  # noqa: SLF001


def test_build_retriever_degrades_when_corpus_missing():
    """A missing corpus must not take the app down — dense retrieval still works."""
    retriever = build_retriever(
        _settings(corpus_dir="./does/not/exist"),
        FakeEmbeddings(), FakeVectorStore(), hybrid=True, rerank=False,
    )
    assert isinstance(retriever, HybridRetriever)
    assert retriever._sparse is None  # noqa: SLF001


def test_build_retriever_defaults_come_from_settings(tmp_path):
    (tmp_path / "faq_a.md").write_text("# A\n\nbody", encoding="utf-8")
    retriever = build_retriever(
        _settings(corpus_dir=str(tmp_path), hybrid_enabled=False, rerank_enabled=False),
        FakeEmbeddings(), FakeVectorStore(),
    )
    assert isinstance(retriever, DenseRetriever)


def test_build_service_wires_dependencies(monkeypatch):
    # Replace the heavy concrete implementations with fakes so the composition root can
    # be exercised without loading a model, Chroma, an LLM, or the corpus.
    monkeypatch.setattr(service_module, "SentenceTransformerEmbeddings",
                        lambda *a, **k: FakeEmbeddings())
    monkeypatch.setattr(service_module, "ChromaVectorStore",
                        lambda *a, **k: FakeVectorStore([make_chunk("a")]))
    monkeypatch.setattr(service_module, "build_llm_provider", lambda s: FakeLLM())

    svc = build_service(_settings(hybrid_enabled=False, rerank_enabled=False))
    assert isinstance(svc, AssistantService)
    assert svc.knowledge_base_size() == 1
    # And a full ask flows through the wired engine.
    ans = svc.ask("PAY-1001 nedir?")
    assert ans.text  # non-empty response from the fake LLM


def test_build_service_passes_embedding_device(monkeypatch):
    captured: dict = {}

    def fake_embeddings(*args, **kwargs):
        captured["kwargs"] = kwargs
        return FakeEmbeddings()

    monkeypatch.setattr(service_module, "SentenceTransformerEmbeddings", fake_embeddings)
    monkeypatch.setattr(service_module, "ChromaVectorStore",
                        lambda *a, **k: FakeVectorStore([make_chunk("a")]))
    monkeypatch.setattr(service_module, "build_llm_provider", lambda s: FakeLLM())

    build_service(_settings(
        hybrid_enabled=False, rerank_enabled=False, embedding_device="cuda",
    ))
    assert captured["kwargs"] == {"device": "cuda"}


def test_build_service_starts_metrics_server_when_enabled(monkeypatch):
    monkeypatch.setattr(service_module, "SentenceTransformerEmbeddings",
                        lambda *a, **k: FakeEmbeddings())
    monkeypatch.setattr(service_module, "ChromaVectorStore",
                        lambda *a, **k: FakeVectorStore([make_chunk("a")]))
    monkeypatch.setattr(service_module, "build_llm_provider", lambda s: FakeLLM())
    calls = []
    monkeypatch.setattr(service_module, "start_metrics_server", lambda port: calls.append(port))

    build_service(_settings(
        hybrid_enabled=False, rerank_enabled=False,
        metrics_enabled=True, metrics_port=9999,
    ))
    assert calls == [9999]


def test_build_service_skips_metrics_server_when_disabled(monkeypatch):
    monkeypatch.setattr(service_module, "SentenceTransformerEmbeddings",
                        lambda *a, **k: FakeEmbeddings())
    monkeypatch.setattr(service_module, "ChromaVectorStore",
                        lambda *a, **k: FakeVectorStore([make_chunk("a")]))
    monkeypatch.setattr(service_module, "build_llm_provider", lambda s: FakeLLM())
    calls = []
    monkeypatch.setattr(service_module, "start_metrics_server", lambda port: calls.append(port))

    build_service(_settings(hybrid_enabled=False, rerank_enabled=False, metrics_enabled=False))
    assert calls == []


def test_build_service_passes_input_guard_flag_to_engine(monkeypatch):
    monkeypatch.setattr(service_module, "SentenceTransformerEmbeddings",
                        lambda *a, **k: FakeEmbeddings())
    monkeypatch.setattr(service_module, "ChromaVectorStore",
                        lambda *a, **k: FakeVectorStore([make_chunk("a")]))
    monkeypatch.setattr(service_module, "build_llm_provider", lambda s: FakeLLM())

    svc = build_service(_settings(
        hybrid_enabled=False, rerank_enabled=False, input_guard_enabled=False,
    ))
    assert svc._engine._input_guard_enabled is False  # noqa: SLF001
