#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Playwright-based website crawler. Connects to CafeScraper fingerprint browser via CDP (see https://docs.cafescraper.com/why-use-playwright)."""
import asyncio
import hashlib
import os
import re
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, urlunparse

from playwright.async_api import async_playwright, Page, Response

try:
    import html2text
    _H2T = html2text.HTML2Text()
    _H2T.ignore_links = False
    _H2T.ignore_images = True
    _H2T.body_width = 0
except ImportError:
    _H2T = None


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


def _extract_text_from_html(html: str) -> str:
    if not html:
        return ""
    if _H2T:
        return _H2T.handle(html).strip()
    # Fallback: strip tags roughly
    return re.sub(r"<[^>]+>", " ", html).strip()


def _hash_content(content: Optional[str]) -> Optional[str]:
    if not content:
        return None
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


async def _get_page_content(
    page: Page,
    extract_mode: str,
    css_selector: Optional[str],
    max_chars: int,
    excerpt_chars: int,
    include_raw: bool,
) -> Tuple[str, Optional[str], str, bool]:
    raw_html = await page.content()
    if css_selector and css_selector.strip():
        try:
            loc = page.locator(css_selector.strip()).first
            if await loc.count() > 0:
                raw_html = await loc.inner_html()
            else:
                raw_html = ""
        except Exception:
            pass

    content_raw = raw_html if include_raw else None
    if extract_mode == "html":
        content = raw_html
    elif extract_mode == "text":
        if css_selector and css_selector.strip():
            try:
                content = await page.locator(css_selector.strip()).first.inner_text()
            except Exception:
                content = _extract_text_from_html(raw_html)
        else:
            try:
                content = await page.locator("body").inner_text()
            except Exception:
                content = _extract_text_from_html(raw_html)
        content = (content or "").strip()
    else:
        content = _extract_text_from_html(raw_html)

    truncated = False
    if max_chars > 0 and len(content) > max_chars:
        content = content[:max_chars]
        truncated = True
    excerpt = content[:excerpt_chars] if excerpt_chars > 0 else ""
    return content, content_raw, excerpt, truncated


async def _get_links(page: Page, base_url: str, same_domain: bool, base_domains: Set[str]) -> Tuple[List[str], List[str]]:
    try:
        hrefs = await page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            return links.map(a => a.href).filter(Boolean);
        }""")
    except Exception:
        hrefs = []
    internal, external = [], []
    for h in hrefs:
        if not isinstance(h, str):
            continue
        norm = _normalize_url(h)
        if not norm:
            continue
        if same_domain and base_domains and urlparse(norm).netloc not in base_domains:
            external.append(norm)
        else:
            internal.append(norm)
    return internal, external


async def run_crawler(
    input_dict: Dict[str, Any],
    *,
    browser_cdp_url: Optional[str] = None,
    log: Any = None,
    push_data: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> None:
    """Crawl with Playwright. On CafeScraper, browser_cdp_url must be set (no local Chromium). For local testing set LOCAL_DEV=1."""
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
    if wait_until not in ("domcontentloaded", "load", "networkidle"):
        wait_until = "domcontentloaded"
    wait_for_selector = (input_dict.get("waitForSelector") or "").strip() or None
    wait_for_timeout_secs = int(input_dict.get("waitForTimeoutSecs") or 30)
    css_selector = (input_dict.get("cssSelector") or "").strip() or None
    crawl_mode = (input_dict.get("crawlMode") or "full").lower()
    include_link_urls = bool(input_dict.get("includeLinkUrls", False))
    max_results = int(input_dict.get("maxResults") or 1000)

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
    timeout_ms = request_timeout_secs * 1000
    push_data = push_data or (lambda x: None)
    log = log or type("Log", (), {"info": lambda s: None, "warning": lambda s: None, "error": lambda s: None, "debug": lambda s: None})()

    async with async_playwright() as p:
        if browser_cdp_url:
            log.info("Connecting to CafeScraper fingerprint browser via CDP")
            try:
                browser = await p.chromium.connect_over_cdp(browser_cdp_url)
            except Exception as e:
                log.error(f"Failed to connect to fingerprint browser: {e}")
                raise
        else:
            log.info("Launching local Chromium (for local testing)")
            browser = await p.chromium.launch(headless=True, args=["--disable-gpu"])

        try:
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
                title = None
                meta_description = None
                content = ""
                content_raw = None
                content_excerpt = ""
                content_truncated = False
                internal_urls: List[str] = []
                external_urls: List[str] = []

                try:
                    context = await browser.new_context()
                    page = await context.new_page()
                    try:
                        response: Optional[Response] = await page.goto(
                            url,
                            timeout=timeout_ms,
                            wait_until=wait_until,
                        )
                        if response:
                            status_code = response.status
                        success = status_code is None or status_code < 400

                        if wait_for_selector:
                            try:
                                await page.wait_for_selector(wait_for_selector, timeout=wait_for_timeout_secs * 1000)
                            except Exception as e:
                                error_message = str(e)
                                success = False

                        if success:
                            title = await page.title()
                            try:
                                meta_el = await page.query_selector('meta[name="description"]')
                                if meta_el:
                                    meta_description = await meta_el.get_attribute("content")
                            except Exception:
                                pass

                            internal_urls, external_urls = await _get_links(page, url, same_domain_only, base_domains)

                            if crawl_mode == "full":
                                content, content_raw, content_excerpt, content_truncated = await _get_page_content(
                                    page, extract_mode, css_selector, max_content_chars, content_excerpt_chars, include_raw_content
                                )
                    finally:
                        await context.close()
                except Exception as e:
                    error_message = str(e)
                    success = False

                if not success and attempt < max_retries:
                    attempts[url] = attempt + 1
                    backoff = min(retry_backoff_secs * (2 ** attempt), 60)
                    await asyncio.sleep(backoff)
                    queue.append((url, depth))
                    continue

                extracted_at = datetime.now(timezone.utc).isoformat()
                _err_type = None if success else ("blocked" if status_code in (401, 403) else ("rate_limited" if status_code == 429 else "network_error"))
                if crawl_mode == "discover_only":
                    item = {
                        "url": url,
                        "success": success,
                        "status_code": status_code,
                        "error_type": _err_type,
                        "title": title,
                        "links_internal_count": len(internal_urls),
                        "links_external_count": len(external_urls),
                        "extracted_at": extracted_at,
                    }
                    if include_link_urls:
                        item["links_internal"] = internal_urls
                        item["links_external"] = external_urls
                else:
                    item = {
                        "url": url,
                        "success": success,
                        "status_code": status_code,
                        "error_message": error_message,
                        "error_type": _err_type,
                        "content": content or None,
                        "content_raw": content_raw,
                        "content_excerpt": content_excerpt,
                        "content_truncated": content_truncated,
                        "title": title,
                        "meta_description": meta_description,
                        "content_length": len(content) if content else 0,
                        "content_hash": _hash_content(content),
                        "links_internal_count": len(internal_urls),
                        "links_external_count": len(external_urls),
                        "extracted_at": extracted_at,
                        "retry_attempt": attempt,
                        "will_retry": False,
                    }
                    if include_link_urls:
                        item["links_internal"] = internal_urls
                        item["links_external"] = external_urls
                push_data(item)
                pushed += 1

                if depth < max_depth and success:
                    for link in internal_urls:
                        if link in seen:
                            continue
                        if include_patterns and not any(r.search(link) for r in include_patterns):
                            continue
                        if exclude_patterns and any(r.search(link) for r in exclude_patterns):
                            continue
                        seen.add(link)
                        attempts[link] = 0
                        queue.append((link, depth + 1))
        finally:
            await browser.close()
