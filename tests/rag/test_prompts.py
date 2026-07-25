"""Tests for prompt assembly."""

from __future__ import annotations

from payment_assistant.models import RetrievedChunk
from payment_assistant.rag.prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from tests.conftest import make_chunk


def test_system_prompt_is_turkish_and_grounded():
    assert "Türkçe" in SYSTEM_PROMPT
    assert "[S1]" in SYSTEM_PROMPT  # instructs citation format


def test_build_user_prompt_numbers_sources():
    retrieved = [
        RetrievedChunk(make_chunk("d1", text="first source"), 0.9),
        RetrievedChunk(make_chunk("d2", 1, text="second source"), 0.8),
    ]
    prompt = build_user_prompt("neden declined?", retrieved)
    assert "SORU:" in prompt and "neden declined?" in prompt
    assert "[S1]" in prompt and "[S2]" in prompt
    assert "first source" in prompt and "second source" in prompt


def test_build_user_prompt_handles_no_sources():
    prompt = build_user_prompt("soru", [])
    assert "Kaynak bulunamadı" in prompt
