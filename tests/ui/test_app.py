"""Tests for UI formatting helpers (no server launch)."""

from __future__ import annotations

import pytest

from payment_assistant.models import Answer, Citation, RetrievedChunk
from payment_assistant.ui.app import _format_answer, build_ui, handle_query
from tests.conftest import make_chunk


def test_format_answer_with_citations():
    ans = Answer(
        text="cevap [S1]",
        citations=[Citation("S1", "errorcodes_payment", "Codes", "error_codes", "e.md", 0.91)],
        retrieved=[RetrievedChunk(make_chunk("errorcodes_payment"), 0.91)],
        redactions=["[CARD]×1"],
    )
    answer_md, sources_md, info_md = _format_answer(ans)
    assert "cevap" in answer_md
    assert "atıf yapılan" in sources_md and "Codes" in sources_md
    assert "[CARD]×1" in info_md


def test_format_answer_retrieved_but_no_citations():
    ans = Answer(
        text="cevap",
        citations=[],
        retrieved=[RetrievedChunk(make_chunk("faq_general", text="x"), 0.5)],
    )
    _, sources_md, info_md = _format_answer(ans)
    assert "atıf yapılmadı" in sources_md
    assert "bulunmadı" in info_md  # no redactions message


def test_format_answer_no_sources():
    ans = Answer(text="cevap", citations=[], retrieved=[])
    _, sources_md, _ = _format_answer(ans)
    assert "Kaynak bulunamadı" in sources_md


def test_format_answer_shows_trace_id_when_present():
    ans = Answer(text="cevap", citations=[], retrieved=[], trace_id="abc123def456")
    _, _, info_md = _format_answer(ans)
    assert "abc123def456" in info_md


def test_format_answer_omits_trace_id_when_absent():
    ans = Answer(text="cevap", citations=[], retrieved=[])  # trace_id defaults to ""
    _, _, info_md = _format_answer(ans)
    assert "trace_id" not in info_md


class _FakeService:
    def __init__(self, answer=None, raises=None):
        self._answer = answer or Answer(text="ok", citations=[], retrieved=[])
        self._raises = raises
        self.received = None

    def ask_with_log_file(self, question, file_path):
        self.received = (question, file_path)
        if self._raises:
            raise self._raises
        return self._answer


def test_build_ui_constructs():
    demo = build_ui(_FakeService())
    assert type(demo).__name__ == "Blocks"


def test_handle_query_empty_inputs_prompts_user():
    svc = _FakeService()
    answer_md, sources_md, info_md = handle_query(svc, "   ", None)
    assert "Lütfen" in answer_md
    assert svc.received is None  # service not called on empty input


def test_handle_query_resolves_string_path():
    svc = _FakeService()
    handle_query(svc, "q", "C:/tmp/log.json")
    assert svc.received == ("q", "C:/tmp/log.json")


def test_handle_query_resolves_object_with_name():
    class Upload:
        name = "/tmp/uploaded.xml"

    svc = _FakeService()
    handle_query(svc, "q", Upload())
    assert svc.received[1] == "/tmp/uploaded.xml"


def test_handle_query_surfaces_errors():
    svc = _FakeService(raises=RuntimeError("ollama down"))
    answer_md, _, _ = handle_query(svc, "q", None)
    assert "hata" in answer_md.lower() and "ollama down" in answer_md
