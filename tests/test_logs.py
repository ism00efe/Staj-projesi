"""Tests for uploaded-log summarization (pure, no I/O)."""

from __future__ import annotations

from payment_assistant.logs import summarize_log


def test_json_summary_extracts_error_fields():
    log = '{"error_code": "PAY-1001", "status": "declined", "amount": 100}'
    summary = summarize_log(log)
    assert "error_code=PAY-1001" in summary
    assert "status=declined" in summary


def test_xml_summary_extracts_error_fields():
    log = (
        "<log><errorCode>PAY-6006</errorCode>"
        "<status>failed</status><message>gateway_timeout</message></log>"
    )
    summary = summarize_log(log)
    assert "errorCode=PAY-6006" in summary
    assert "message=gateway_timeout" in summary


def test_raw_fallback_for_unstructured_text():
    log = "java.lang.NullPointerException at CaptureWorker.java:87"
    summary = summarize_log(log)
    assert "NullPointerException" in summary


def test_empty_log():
    assert summarize_log("") == ""
    assert summarize_log("   ") == ""
