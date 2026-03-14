#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crawl4AI-based crawler with CDP support for CafeScraper. Uses BrowserConfig(browser_mode=\"custom\", cdp_url=...) per https://docs.crawl4ai.com/api/parameters/."""
import asyncio
import hashlib
import os
import re
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, urlunparse

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    VirtualScrollConfig,
)


def _normalize_url(url: Optional[str]) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return None
    if not parsed.netloc:
        return None
    return urlunparse(parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), fragment=""))


def _compile_patterns(patterns: List[str]) -> List[re.Pattern]:
    out = []
    for p in patterns or []:
        if not p:
            continue
        try:
            out.append(re.compile(p))
        except re.error:
            pass
    return out


def _link_urls(links_list: List[Any]) -> List[str]:
    out = []
    for link in links_list or []:
        href = link if isinstance(link, str) else (link.get("href") if isinstance(link, dict) else None)
        u = _normalize_url(href) if href else None
        if u:
            out.append(u)
    return out


def _classify_error(status_code: Optional[int], error_message: Optional[str], success: bool) -> Optional[str]:
    if success:
        return None
    if status_code == 429:
        return "rate_limited"
    if status_code in (401, 403):
        return "blocked"
    if status_code and 400 <= status_code < 500:
        return "page_error"
    if status_code and status_code >= 500:
        return "network_error"
    if error_message and ("timeout" in error_message.lower() or "timed out" in error_message.lower()):
        return "network_error"
    return "network_error"


async def run_crawler(
    input_dict: Dict[str, Any],
    *,
    browser_cdp_url: Optional[str] = None,
    log: Any = None,
    push_data: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> None:
    """Crawl with crawl4ai. On CafeScraper, browser_cdp_url must be set (no local Chromium). For local testing set LOCAL_DEV=1."""
    if not browser_cdp_url and not os.environ.get("LOCAL_DEV"):
        raise ValueError(
            "CDP URL required: CafeScraper does not support local Chromium. Set PROXY_AUTH or LOCAL_DEV=1 for local testing."
        )
    start_urls = input_dict.get("startUrls") or []
    max_pages = int(input_dict.get("maxPages") or 50)
    max_depth = int(input_dict.get("maxDepth") or 2)
    request_timeout_secs = int(input_dict.get("requestTimeoutSecs") or 60)
    extract_mode = (input_dict.get("extractMode") or "markdown").lower()
    same_domain_only = bool(input_dict.get("sameDomainOnly", True))
    include_patterns = _compile_patterns(input_dict.get("includePatterns") or [])
    exclude_patterns = _compile_patterns(input_dict.get("excludePatterns") or [])
    max_retries = int(input_dict.get("maxRetries") or 2)
    retry_backoff_secs = int(input_dict.get("retryBackoffSecs") or 2)
    max_content_chars = int(input_dict.get("maxContentChars") or 0)
    content_excerpt_chars = int(input_dict.get("contentExcerptChars") or 300)
    include_raw_content = bool(input_dict.get("includeRawContent", False))
    wait_until = (input_dict.get("waitUntil") or "domcontentloaded").lower()
    wait_for_selector = (input_dict.get("waitForSelector") or "").strip() or None
    wait_for_timeout_secs = int(input_dict.get("waitForTimeoutSecs") or 30)
    css_selector = (input_dict.get("cssSelector") or "").strip() or None
    crawl_mode = (input_dict.get("crawlMode") or "full").lower()
    include_link_urls = bool(input_dict.get("includeLinkUrls", False))
    max_results = int(input_dict.get("maxResults") or 1000)
    word_count_threshold = int(input_dict.get("wordCountThreshold") or 0)
    virtual_scroll_selector = (input_dict.get("virtualScrollSelector") or "").strip() or None
    virtual_scroll_count = int(input_dict.get("virtualScrollCount") or 10)
    clean_content = bool(input_dict.get("cleanContent", True))

    if extract_mode not in ("html", "text", "markdown"):
        extract_mode = "markdown"
    if crawl_mode not in ("full", "discover_only"):
        crawl_mode = "full"

    normalized_start = []
    for u in start_urls:
        n = _normalize_url(u)
        if n:
            normalized_start.append(n)
    if not normalized_start:
        raise ValueError("No valid startUrls (http/https required).")

    base_domains = {urlparse(u).netloc for u in normalized_start if urlparse(u).netloc}
    push_data = push_data or (lambda x: None)
    log = log or type("Log", (), {"info": lambda s: None, "warning": lambda s: None, "error": lambda s: None, "debug": lambda s: None})()

    # BrowserConfig: CDP when CafeScraper provides URL, else local headless (https://docs.crawl4ai.com/api/parameters/)
    if browser_cdp_url:
        log.info("Using crawl4ai with CafeScraper fingerprint browser (CDP)")
        browser_config = BrowserConfig(
            browser_type="chromium",
            browser_mode="custom",
            cdp_url=browser_cdp_url,
        )
    else:
        log.info("Using crawl4ai with local Chromium (for local testing)")
        browser_config = BrowserConfig(headless=True)

    page_timeout_ms = request_timeout_secs * 1000
    run_config_kwargs: Dict[str, Any] = {
        "cache_mode": CacheMode.BYPASS,
        "stream": True,
        "wait_until": wait_until,
        "page_timeout": page_timeout_ms,
    }
    if word_count_threshold > 0:
        run_config_kwargs["word_count_threshold"] = word_count_threshold
    if wait_for_selector:
        run_config_kwargs["wait_for"] = f"css:{wait_for_selector}" if not wait_for_selector.startswith(("css:", "js:")) else wait_for_selector
        run_config_kwargs["wait_for_timeout"] = wait_for_timeout_secs * 1000
    if css_selector:
        run_config_kwargs["css_selector"] = css_selector
    if virtual_scroll_selector:
        run_config_kwargs["virtual_scroll_config"] = VirtualScrollConfig(
            container_selector=virtual_scroll_selector,
            scroll_count=virtual_scroll_count,
            scroll_by="container_height",
            wait_after_scroll=0.5,
        )
    run_config = CrawlerRunConfig(**run_config_kwargs)

    def _extract_content(result: Any) -> Tuple[str, Optional[str], str, bool]:
        raw = None
        if extract_mode == "html":
            raw = getattr(result, "cleaned_html", None) or getattr(result, "html", None)
        elif extract_mode == "text":
            raw = getattr(result, "text", None) or getattr(result, "cleaned_text", None)
            if not raw and hasattr(result, "markdown") and result.markdown:
                raw = getattr(result.markdown, "raw_markdown", None) or str(result.markdown)
        else:
            md = getattr(result, "markdown", None)
            if md:
                raw = getattr(md, "raw_markdown", None) or getattr(md, "fit_markdown", None) or str(md)
        content = raw or ""
        if clean_content and content and extract_mode == "markdown":
            content = content.strip()
        if max_content_chars > 0 and len(content) > max_content_chars:
            content = content[:max_content_chars]
            truncated = True
        else:
            truncated = False
        excerpt = content[:content_excerpt_chars] if content_excerpt_chars > 0 else ""
        return content, raw if include_raw_content else None, excerpt, truncated

    def _meta(result: Any) -> Dict[str, Optional[str]]:
        meta = getattr(result, "metadata", None) or {}
        return {
            "title": meta.get("title") or meta.get("meta_title"),
            "meta_description": meta.get("description") or meta.get("meta_description"),
        }

    async with AsyncWebCrawler(config=browser_config) as crawler:
        seen: Set[str] = set()
        queue: deque = deque()
        attempts: Dict[str, int] = {}
        for u in normalized_start:
            if u not in seen:
                seen.add(u)
                attempts[u] = 0
                queue.append((u, 0))

        pushed = 0
        while queue and pushed < max_results:
            url, depth = queue.popleft()
            if depth > max_depth:
                continue

            attempt = attempts.get(url, 0)
            success = False
            status_code = None
            error_message = None
            result = None

            try:
                result = await crawler.arun(url, config=run_config)
                success = bool(getattr(result, "success", False))
                status_code = getattr(result, "status_code", None)
                error_message = getattr(result, "error_message", None)
            except Exception as e:
                error_message = str(e)
                success = False

            if not success and attempt < max_retries:
                attempts[url] = attempt + 1
                await asyncio.sleep(min(retry_backoff_secs * (2 ** attempt), 60))
                queue.append((url, depth))
                continue

            extracted_at = datetime.now(timezone.utc).isoformat()
            meta = _meta(result) if result else {}
            links = getattr(result, "links", None) or {}
            internal = _link_urls(links.get("internal", []) if isinstance(links, dict) else [])
            external = _link_urls(links.get("external", []) if isinstance(links, dict) else [])

            if crawl_mode == "discover_only":
                item = {
                    "url": url,
                    "success": success,
                    "status_code": status_code,
                    "error_type": _classify_error(status_code, error_message, success),
                    "title": meta.get("title"),
                    "links_internal_count": len(internal),
                    "links_external_count": len(external),
                    "extracted_at": extracted_at,
                }
                if include_link_urls:
                    item["links_internal"] = internal
                    item["links_external"] = external
            else:
                content, content_raw, content_excerpt, content_truncated = "", None, "", False
                if result and success:
                    content, content_raw, content_excerpt, content_truncated = _extract_content(result)
                content_hash = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest() if content else None
                item = {
                    "url": url,
                    "success": success,
                    "status_code": status_code,
                    "error_message": error_message,
                    "error_type": _classify_error(status_code, error_message, success),
                    "content": content or None,
                    "content_raw": content_raw,
                    "content_excerpt": content_excerpt,
                    "content_truncated": content_truncated,
                    "title": meta.get("title"),
                    "meta_description": meta.get("meta_description"),
                    "content_length": len(content) if content else 0,
                    "content_hash": content_hash,
                    "links_internal_count": len(internal),
                    "links_external_count": len(external),
                    "extracted_at": extracted_at,
                    "retry_attempt": attempt,
                    "will_retry": False,
                }
                if include_link_urls:
                    item["links_internal"] = internal
                    item["links_external"] = external
            push_data(item)
            pushed += 1

            if depth < max_depth and success and result:
                for link in internal:
                    if link in seen:
                        continue
                    if base_domains and same_domain_only and urlparse(link).netloc not in base_domains:
                        continue
                    if include_patterns and not any(r.search(link) for r in include_patterns):
                        continue
                    if exclude_patterns and any(r.search(link) for r in exclude_patterns):
                        continue
                    seen.add(link)
                    attempts[link] = 0
                    queue.append((link, depth + 1))
