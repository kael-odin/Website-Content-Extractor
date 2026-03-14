#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CafeScraper worker: Website content extractor. Uses crawl4ai + CDP when available (https://docs.crawl4ai.com/api/parameters/, https://docs.cafescraper.com/why-use-playwright)."""
import asyncio
import os

from sdk import CafeSDK

try:
    from crawler_c4ai import run_crawler
    _CRAWLER_BACKEND = "crawl4ai"
except ImportError:
    from scraper import run_crawler
    _CRAWLER_BACKEND = "playwright"

RESULT_TABLE_HEADERS = [
    {"label": "URL", "key": "url", "format": "text"},
    {"label": "Success", "key": "success", "format": "boolean"},
    {"label": "Status code", "key": "status_code", "format": "integer"},
    {"label": "Error message", "key": "error_message", "format": "text"},
    {"label": "Error type", "key": "error_type", "format": "text"},
    {"label": "Content", "key": "content", "format": "text"},
    {"label": "Content raw", "key": "content_raw", "format": "text"},
    {"label": "Content excerpt", "key": "content_excerpt", "format": "text"},
    {"label": "Content truncated", "key": "content_truncated", "format": "boolean"},
    {"label": "Title", "key": "title", "format": "text"},
    {"label": "Meta description", "key": "meta_description", "format": "text"},
    {"label": "Content length", "key": "content_length", "format": "integer"},
    {"label": "Content hash", "key": "content_hash", "format": "text"},
    {"label": "Links internal count", "key": "links_internal_count", "format": "integer"},
    {"label": "Links external count", "key": "links_external_count", "format": "integer"},
    {"label": "Extracted at", "key": "extracted_at", "format": "text"},
    {"label": "Retry attempt", "key": "retry_attempt", "format": "integer"},
    {"label": "Will retry", "key": "will_retry", "format": "boolean"},
    {"label": "Links internal", "key": "links_internal", "format": "array"},
    {"label": "Links external", "key": "links_external", "format": "array"},
]
HEADER_KEYS = [h["key"] for h in RESULT_TABLE_HEADERS]


def _normalize_start_urls(value):
    """Normalize startUrls from various shapes to a list of URL strings.

    Accepts:
    - list of strings: ["https://...", ...]
    - list of dicts: [{"url": "https://..."}, {"string": "https://..."}]
    - single dict: {"url": "https://..."} (CafeScraper/requestList edge case)
    - single string: "https://..."
    """
    if not value:
        return []
    # Single dict -> wrap to list
    if isinstance(value, dict):
        value = [value]
    # Single string -> wrap to list
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for x in value:
        if isinstance(x, str):
            u = x.strip()
            if u:
                out.append(u)
        elif isinstance(x, dict):
            u = (x.get("url") or x.get("string") or "").strip()
            if u:
                out.append(u)
    return out


def _row_for_push(item: dict) -> dict:
    return {k: item.get(k) if isinstance(item.get(k), (list, dict, str, int, float, bool, type(None))) else str(item.get(k)) for k in HEADER_KEYS}


DEFAULT_INPUT = {
    "startUrls": [],
    "maxPages": 50,
    "maxDepth": 2,
    "requestTimeoutSecs": 60,
    "extractMode": "markdown",
    "maxResults": 1000,
    "sameDomainOnly": True,
    "includePatterns": [],
    "excludePatterns": [],
    "maxRetries": 2,
    "retryBackoffSecs": 2,
    "includeRawContent": False,
    "maxContentChars": 0,
    "contentExcerptChars": 300,
    "waitUntil": "domcontentloaded",
    "waitForSelector": "",
    "waitForTimeoutSecs": 30,
    "cssSelector": "",
    "crawlMode": "full",
    "includeLinkUrls": False,
    "cleanContent": True,
    "virtualScrollSelector": "",
    "virtualScrollCount": 10,
    "wordCountThreshold": 0,
}

# CafeScraper: Playwright must connect to remote fingerprint browser; local Chromium is not available.
# Set LOCAL_DEV=1 only when testing locally with Chromium installed.
REQUIRE_CDP = "PROXY_AUTH is required. On CafeScraper, Playwright must connect to the remote fingerprint browser; local Chromium is not available. For local testing only, set environment variable LOCAL_DEV=1."


def _validate_and_clamp(input_dict: dict) -> None:
    """Clamp numeric inputs to schema bounds and normalize enums."""
    input_dict["maxPages"] = max(1, min(10000, int(input_dict.get("maxPages") or 50)))
    input_dict["maxDepth"] = max(0, min(10, int(input_dict.get("maxDepth") or 2)))
    input_dict["requestTimeoutSecs"] = max(5, min(600, int(input_dict.get("requestTimeoutSecs") or 60)))
    input_dict["maxResults"] = max(1, min(200000, int(input_dict.get("maxResults") or 1000)))
    input_dict["maxRetries"] = max(0, min(10, int(input_dict.get("maxRetries") or 2)))
    input_dict["retryBackoffSecs"] = max(0, min(120, int(input_dict.get("retryBackoffSecs") or 2)))
    input_dict["contentExcerptChars"] = max(0, min(5000, int(input_dict.get("contentExcerptChars") or 300)))
    input_dict["maxContentChars"] = max(0, min(500000, int(input_dict.get("maxContentChars") or 0)))
    input_dict["waitForTimeoutSecs"] = max(1, min(300, int(input_dict.get("waitForTimeoutSecs") or 30)))
    e = (input_dict.get("extractMode") or "markdown").lower()
    input_dict["extractMode"] = e if e in ("markdown", "html", "text") else "markdown"
    c = (input_dict.get("crawlMode") or "full").lower()
    input_dict["crawlMode"] = c if c in ("full", "discover_only") else "full"
    w = (input_dict.get("waitUntil") or "domcontentloaded").lower()
    input_dict["waitUntil"] = w if w in ("domcontentloaded", "load", "networkidle") else "domcontentloaded"


async def run():
    try:
        raw = CafeSDK.Parameter.get_input_json_dict() or {}
        CafeSDK.Log.debug(f"Raw input JSON from CafeScraper: {raw}")
        raw = {k: v for k, v in raw.items() if k != "version"}
        input_dict = {**DEFAULT_INPUT, **raw}

        # CafeScraper currently sends single URL as top-level 'url' field, even if input_schema defines startUrls.
        raw_urls = (
            input_dict.get("startUrls")
            or input_dict.get("start_urls")
            or input_dict.get("starturls")
            or input_dict.get("url")
        )
        start_urls = _normalize_start_urls(raw_urls)
        CafeSDK.Log.debug(f"Normalized startUrls: {start_urls}")
        if not start_urls:
            CafeSDK.Log.error("Missing required input: startUrls.")
            CafeSDK.Result.push_data({"error": "Missing startUrls", "error_code": "400", "status": "failed"})
            return
        input_dict["startUrls"] = start_urls

        for key in ("includePatterns", "excludePatterns"):
            val = input_dict.get(key)
            if val and isinstance(val, list) and val and isinstance(val[0], dict) and "string" in (val[0] or {}):
                input_dict[key] = [x.get("string", "").strip() for x in val if x and x.get("string")]

        _validate_and_clamp(input_dict)

        # CafeScraper: must use remote fingerprint browser via CDP; local Chromium is not available.
        auth = os.environ.get("PROXY_AUTH")
        browser_cdp_url = f"ws://{auth}@chrome-ws-inner.cafescraper.com" if auth else None
        if not browser_cdp_url and not os.environ.get("LOCAL_DEV"):
            CafeSDK.Log.error(REQUIRE_CDP)
            CafeSDK.Result.push_data({
                "error": REQUIRE_CDP,
                "error_code": "400",
                "status": "failed",
            })
            return
        if browser_cdp_url:
            CafeSDK.Log.info("Connecting to CafeScraper fingerprint browser via CDP")
        else:
            CafeSDK.Log.info("LOCAL_DEV=1: using local Chromium (local testing only)")
        CafeSDK.Log.debug(f"Crawler backend: {_CRAWLER_BACKEND}")

        CafeSDK.Result.set_table_header(RESULT_TABLE_HEADERS)
        CafeSDK.Log.info(f"Starting crawl: {len(start_urls)} start URL(s), maxPages={input_dict['maxPages']}, maxDepth={input_dict['maxDepth']}")

        class _Log:
            @staticmethod
            def info(msg): CafeSDK.Log.info(msg)
            @staticmethod
            def warning(msg): CafeSDK.Log.warn(msg)
            @staticmethod
            def error(msg): CafeSDK.Log.error(msg)
            @staticmethod
            def debug(msg): CafeSDK.Log.debug(msg)

        def push(item):
            CafeSDK.Result.push_data(_row_for_push(item))

        await run_crawler(input_dict, browser_cdp_url=browser_cdp_url, log=_Log(), push_data=push)
        CafeSDK.Log.info("Run completed")
    except Exception as e:
        msg = str(e) if e else "Unknown error"
        CafeSDK.Log.error(f"Run error: {msg}")
        try:
            CafeSDK.Result.push_data({"error": msg, "error_code": "500", "status": "failed"})
        except Exception:
            pass
        raise


if __name__ == "__main__":
    asyncio.run(run())
