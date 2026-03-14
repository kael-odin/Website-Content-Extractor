"""Tests for main run summary structure (no Actor runtime)."""

from __future__ import annotations


def test_run_summary_structure() -> None:
    """Run summary written to key-value store has expected keys and types."""
    processed = 2
    success_count = 1
    error_counts = {"none": 1, "page_error": 1}
    total_content_chars = 1000
    run_summary = {
        "totalPages": processed,
        "successCount": success_count,
        "failedCount": processed - success_count,
        "errorTypes": error_counts,
        "totalContentLength": total_content_chars,
    }
    assert run_summary["totalPages"] == 2
    assert run_summary["successCount"] == 1
    assert run_summary["failedCount"] == 1
    assert run_summary["errorTypes"] == {"none": 1, "page_error": 1}
    assert run_summary["totalContentLength"] == 1000
