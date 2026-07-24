"""Tests for the synthetic data generator."""

from __future__ import annotations

from payment_assistant.datagen import generate_corpus


def test_generate_corpus_writes_files(tmp_path):
    count = generate_corpus(str(tmp_path))
    files = list(tmp_path.glob("*"))
    assert count == len(files) > 10  # a meaningful corpus


def test_generated_content_is_realistic(tmp_path):
    generate_corpus(str(tmp_path))
    codes = (tmp_path / "errorcodes_payment.md").read_text(encoding="utf-8")
    assert "PAY-1001" in codes and "insufficient_funds" in codes


def test_log_sample_contains_pii_for_sanitization_demo(tmp_path):
    # datagen writes RAW logs; sanitization happens at ingestion, not here.
    generate_corpus(str(tmp_path))
    log = (tmp_path / "log_declined_payment.json").read_text(encoding="utf-8")
    assert "4111 1111 1111 1111" in log  # a Luhn-valid test card to be masked later


def test_generate_corpus_is_idempotent(tmp_path):
    assert generate_corpus(str(tmp_path)) == generate_corpus(str(tmp_path))
