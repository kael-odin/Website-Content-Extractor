#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CafeScraper worker: Website content extractor. Entry: main.py. Uses CafeSDK for params, logging, result push."""
import asyncio
import os
import sys
from pathlib import Path

# Ensure src is on path so we can import crawl4ai_actor
_root = Path(__file__).resolve().parent
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))

from pydantic import ValidationError

from sdk import CafeSDK

# After path setup
from crawl4ai_actor.config import ActorInput
from crawl4ai_actor.crawler import crawl_urls

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


def _normalize_start_urls(value):
    """Normalize startUrls from CafeScraper requestList [{"url": "..."}] or stringList [{"string": "..."}] to list of strings."""
    if not value or not isinstance(value, list):
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
    """Ensure item is JSON-serializable and only includes known keys."""
    keys = [h["key"] for h in RESULT_TABLE_HEADERS]
    out = {}
    for k in keys:
        v = item.get(k)
        if v is None or isinstance(v, (str, int, float, bool, list, dict)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


# Defaults when platform sends minimal input
DEFAULT_INPUT = {
    "startUrls": [],
    "maxPages": 50,
    "maxDepth": 2,
    "concurrency": 5,
    "requestTimeoutSecs": 60,
    "headless": True,
    "useProxy": False,
    "proxyGroups": None,
    "extractMode": "markdown",
    "maxResults": 1000,
    "sameDomainOnly": True,
    "includePatterns": [],
    "excludePatterns": [],
    "maxRetries": 2,
    "retryBackoffSecs": 2,
    "maxRequestsPerMinute": 0,
    "enableStealth": False,
    "userAgent": None,
    "cleanContent": True,
    "includeRawContent": False,
    "maxContentChars": 0,
    "contentExcerptChars": 300,
    "wordCountThreshold": 0,
    "virtualScrollSelector": None,
    "virtualScrollCount": 10,
    "waitUntil": "domcontentloaded",
    "pageLoadWaitSecs": 0,
    "waitForSelector": None,
    "waitForTimeoutSecs": 30,
    "cssSelector": None,
    "crawlMode": "full",
    "includeLinkUrls": False,
}


async def run():
    try:
        raw = CafeSDK.Parameter.get_input_json_dict() or {}
        raw = {k: v for k, v in raw.items() if k != "version"}
        input_dict = {**DEFAULT_INPUT, **raw}

        # Normalize startUrls (requestList / stringList → list of URL strings)
        start_urls = _normalize_start_urls(input_dict.get("startUrls"))
        if not start_urls:
            CafeSDK.Log.error(
                "Missing required input: startUrls. Example: [{\"url\": \"https://example.com\"}] or [\"https://example.com\"]"
            )
            CafeSDK.Result.push_data({"error": "Missing startUrls", "error_code": "400", "status": "failed"})
            return
        input_dict["startUrls"] = start_urls

        # Normalize stringList arrays if present
        for key in ("includePatterns", "excludePatterns", "proxyGroups"):
            val = input_dict.get(key)
            if val and isinstance(val, list) and val and isinstance(val[0], dict) and "string" in (val[0] or {}):
                input_dict[key] = [x.get("string", "").strip() for x in val if x and x.get("string")]

        try:
            actor_input = ActorInput(**input_dict)
        except ValidationError as e:
            errs = e.errors()
            msg = errs[0].get("msg", str(e)) if errs else str(e)
            loc = errs[0].get("loc", ())
            hint = f" {loc[0]}: {msg}" if loc else f" {msg}"
            CafeSDK.Log.error(f"Invalid input:{hint}")
            CafeSDK.Result.push_data({"error": f"Invalid input:{hint}", "error_code": "400", "status": "failed"})
            return

        # Proxy: use platform proxy when PROXY_AUTH is set (CafeScraper)
        auth = os.environ.get("PROXY_AUTH")
        proxy_url = f"socks5://{auth}@proxy-inner.cafescraper.com:6000" if auth else None
        if proxy_url:
            CafeSDK.Log.info("Using CafeScraper proxy from PROXY_AUTH")
        if actor_input.use_proxy and not proxy_url:
            CafeSDK.Log.warn("useProxy is true but PROXY_AUTH not set; running without proxy")

        CafeSDK.Result.set_table_header(RESULT_TABLE_HEADERS)
        CafeSDK.Log.info(f"Starting crawl: {len(actor_input.start_urls)} start URL(s), maxPages={actor_input.max_pages}")

        processed = 0
        async for item in crawl_urls(
            start_urls=actor_input.start_urls,
            max_pages=actor_input.max_pages,
            max_depth=actor_input.max_depth,
            concurrency=actor_input.concurrency,
            request_timeout_secs=actor_input.request_timeout_secs,
            headless=actor_input.headless,
            proxy_url=proxy_url,
            extract_mode=actor_input.extract_mode,
            same_domain_only=actor_input.same_domain_only,
            include_patterns=actor_input.include_patterns,
            exclude_patterns=actor_input.exclude_patterns,
            max_retries=actor_input.max_retries,
            retry_backoff_secs=actor_input.retry_backoff_secs,
            max_requests_per_minute=actor_input.max_requests_per_minute,
            enable_stealth=actor_input.enable_stealth,
            user_agent=actor_input.user_agent,
            clean_content=actor_input.clean_content,
            include_raw_content=actor_input.include_raw_content,
            max_content_chars=actor_input.max_content_chars,
            content_excerpt_chars=actor_input.content_excerpt_chars,
            word_count_threshold=actor_input.word_count_threshold,
            virtual_scroll_selector=actor_input.virtual_scroll_selector,
            virtual_scroll_count=actor_input.virtual_scroll_count,
            wait_until=actor_input.wait_until,
            page_load_wait_secs=actor_input.page_load_wait_secs,
            wait_for_selector=actor_input.wait_for_selector,
            wait_for_timeout_secs=actor_input.wait_for_timeout_secs,
            css_selector=actor_input.css_selector,
            crawl_mode=actor_input.crawl_mode,
            include_link_urls=actor_input.include_link_urls,
        ):
            CafeSDK.Result.push_data(_row_for_push(item))
            processed += 1
            if processed >= actor_input.max_results:
                break

        CafeSDK.Log.info(f"Run completed: {processed} item(s) pushed")
    except Exception as e:
        CafeSDK.Log.error(f"Run error: {e}")
        CafeSDK.Result.push_data({"error": str(e), "error_code": "500", "status": "failed"})
        raise


if __name__ == "__main__":
    asyncio.run(run())
