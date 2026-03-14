from __future__ import annotations

import pytest

from crawl4ai_actor.crawler import (
    _classify_error,
    _clean_markdown,
    _compile_patterns,
    _normalize_url,
    _normalize_wait_for,
)


def test_normalize_url_strips_fragment_and_lowercases() -> None:
    assert (
        _normalize_url("HTTPS://Example.COM/Path?a=1#section") == "https://example.com/Path?a=1"
    )


def test_normalize_url_rejects_non_http_schemes() -> None:
    assert _normalize_url("mailto:test@example.com") is None
    assert _normalize_url("javascript:alert(1)") is None
    assert _normalize_url("file:///etc/passwd") is None


def test_normalize_wait_for_returns_none_for_empty() -> None:
    assert _normalize_wait_for(None) is None
    assert _normalize_wait_for("") is None
    assert _normalize_wait_for("   ") is None


def test_normalize_wait_for_passes_through_css_js_prefix() -> None:
    assert _normalize_wait_for("css:.article") == "css:.article"
    assert _normalize_wait_for("js:() => true") == "js:() => true"


def test_normalize_wait_for_adds_css_prefix_for_plain_selector() -> None:
    assert _normalize_wait_for(".main") == "css:.main"
    assert _normalize_wait_for("  #content  ") == "css:#content"


def test_normalize_url_rejects_relative_or_blank() -> None:
    assert _normalize_url("") is None
    assert _normalize_url("   ") is None
    assert _normalize_url("/relative/path") is None
    assert _normalize_url("example.com") is None


def test_compile_patterns_accepts_valid_patterns() -> None:
    pats = _compile_patterns([r"/docs", r"^https?://"], "includePatterns")
    assert len(pats) == 2


def test_compile_patterns_rejects_invalid_patterns() -> None:
    with pytest.raises(ValueError) as exc:
        _compile_patterns([r"(", r"[a-"], "excludePatterns")
    assert "excludePatterns" in str(exc.value)


def test_clean_markdown_removes_nav_and_link_noise() -> None:
    content = """
    Skip to content
    - [Home](/)
    - [Docs](/docs)

    # Title
    Some real text here.
    [Read more](/more)
    """
    cleaned = _clean_markdown(content)
    assert "Skip to content" not in cleaned
    assert "Home" not in cleaned
    assert "Docs" not in cleaned
    assert "Title" in cleaned
    assert "Some real text here." in cleaned


def test_classify_error_rate_limited() -> None:
    assert _classify_error(429, "Too Many Requests", success=False) == "rate_limited"


def test_classify_error_blocked() -> None:
    assert _classify_error(403, "Forbidden", success=False) == "blocked"
