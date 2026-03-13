from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig


def _extract_content(result: Any, extract_mode: str) -> str | None:
    if extract_mode == "html":
        return getattr(result, "cleaned_html", None) or getattr(result, "html", None)

    if extract_mode == "text":
        return (
            getattr(result, "text", None)
            or getattr(result, "cleaned_text", None)
            or _extract_content(result, "markdown")
        )

    markdown_obj = getattr(result, "markdown", None)
    if markdown_obj is None:
        return None
    return getattr(markdown_obj, "raw_markdown", None) or str(markdown_obj)


def _extract_metadata(result: Any) -> dict:
    metadata = getattr(result, "metadata", None) or {}
    title = metadata.get("title")
    description = metadata.get("description") or metadata.get("meta_description")
    return {
        "title": title,
        "meta_description": description,
    }


def _hash_content(content: str | None) -> str | None:
    if not content:
        return None
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def _clean_markdown(content: str) -> str:
    lines = [line.strip() for line in content.splitlines()]
    cleaned: list[str] = []
    last_line = None
    for line in lines:
        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        lower = line.lower()
        if "skip to content" in lower:
            continue
        if lower in {"back", "log in", "login", "sign up", "get started"}:
            continue
        if line.startswith(("* [", "- [", "+ [")) and len(line) < 200:
            continue
        link_density = (line.count("](") * 4) / max(len(line), 1)
        if link_density > 0.4 and len(line) < 200:
            continue
        if last_line == line:
            continue
        cleaned.append(line)
        last_line = line
    return "\n".join(cleaned).strip()


def _apply_truncation(content: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(content) <= max_chars:
        return content, False
    return content[:max_chars], True


def _make_excerpt(content: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    return content[:max_chars]


def _classify_error(
    status_code: int | None, error_message: str | None, success: bool
) -> str | None:
    if success:
        return None
    if status_code is not None:
        if 400 <= status_code < 500:
            return "page_error"
        if status_code >= 500:
            return "network_error"
    if error_message:
        message = error_message.lower()
        if "timeout" in message or "timed out" in message:
            return "network_error"
        if "connection" in message or "dns" in message:
            return "network_error"
        if "parse" in message or "extract" in message:
            return "parse_error"
        if "codec" in message or "encode" in message or "decode" in message:
            return "parse_error"
    return "network_error"


async def _iter_results(
    crawler: AsyncWebCrawler,
    urls: list[str],
    run_config: CrawlerRunConfig,
) -> AsyncIterator[Any]:
    stream = await crawler.arun_many(urls, config=run_config)
    if hasattr(stream, "__aiter__"):
        async for result in stream:
            yield result
    else:
        for result in stream:
            yield result


async def crawl_urls(
    start_urls: list[str],
    max_pages: int,
    max_depth: int,
    concurrency: int,
    request_timeout_secs: int,
    headless: bool,
    proxy_url: str | None,
    extract_mode: str,
    same_domain_only: bool,
    include_patterns: list[str],
    exclude_patterns: list[str],
    max_retries: int,
    retry_backoff_secs: int,
    max_requests_per_minute: int,
    enable_stealth: bool,
    user_agent: str | None,
    clean_content: bool,
    include_raw_content: bool,
    max_content_chars: int,
    content_excerpt_chars: int,
) -> AsyncIterator[dict]:
    browser_kwargs = {
        "headless": headless,
        "proxy": proxy_url,
        "enable_stealth": enable_stealth,
        "verbose": False,
    }
    if user_agent:
        browser_kwargs["user_agent"] = user_agent
    browser_config = BrowserConfig(**browser_kwargs)
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        stream=True,
        semaphore_count=concurrency,
        page_timeout=int(request_timeout_secs * 1000),
    )

    include_regexes = [re.compile(pattern) for pattern in include_patterns if pattern]
    exclude_regexes = [re.compile(pattern) for pattern in exclude_patterns if pattern]
    base_domains = {urlparse(url).netloc for url in start_urls if urlparse(url).netloc}

    async with AsyncWebCrawler(config=browser_config) as crawler:
        seen: set[str] = set()
        frontier: list[tuple[str, int]] = []
        attempts: dict[str, int] = {}
        for url in start_urls:
            if url not in seen:
                seen.add(url)
                attempts[url] = 0
                frontier.append((url, 0))

        processed_requests = 0
        window_start = time.monotonic()
        window_count = 0

        while frontier and processed_requests < max_pages:
            current_depth = frontier[0][1]
            if current_depth > max_depth:
                break

            batch: list[str] = []
            next_frontier: list[tuple[str, int]] = []

            remaining = max_pages - processed_requests
            if max_requests_per_minute > 0:
                elapsed = time.monotonic() - window_start
                if elapsed >= 60:
                    window_start = time.monotonic()
                    window_count = 0
                remaining_in_window = max_requests_per_minute - window_count
                if remaining_in_window <= 0:
                    sleep_for = max(0, 60 - elapsed)
                    if sleep_for:
                        await asyncio.sleep(sleep_for)
                    window_start = time.monotonic()
                    window_count = 0
                    remaining_in_window = max_requests_per_minute
                remaining = min(remaining, remaining_in_window)
            while frontier and frontier[0][1] == current_depth and len(batch) < remaining:
                url, depth = frontier.pop(0)
                if depth != current_depth:
                    frontier.insert(0, (url, depth))
                    break
                batch.append(url)

            async for result in _iter_results(crawler, batch, run_config):
                processed_requests += 1
                url_value = getattr(result, "url", None)
                attempt = attempts.get(url_value, 0) if url_value else 0
                success = bool(getattr(result, "success", False))
                status_code = getattr(result, "status_code", None)
                error_message = getattr(result, "error_message", None)
                raw_content = _extract_content(result, extract_mode)
                content = raw_content or ""
                if clean_content and raw_content:
                    content = _clean_markdown(raw_content)
                content, content_truncated = _apply_truncation(content, max_content_chars)
                content_excerpt = _make_excerpt(content, content_excerpt_chars)
                meta = _extract_metadata(result)
                links = getattr(result, "links", {}) or {}
                internal_links = links.get("internal", []) if isinstance(links, dict) else []
                external_links = links.get("external", []) if isinstance(links, dict) else []
                error_type = _classify_error(status_code, error_message, success)
                will_retry = False
                if not success and url_value and attempt < max_retries:
                    attempts[url_value] = attempt + 1
                    backoff = min(retry_backoff_secs * (2**attempt), 60)
                    if backoff > 0:
                        await asyncio.sleep(backoff)
                    frontier.append((url_value, current_depth))
                    will_retry = True

                yield {
                    "url": url_value,
                    "success": getattr(result, "success", None),
                    "status_code": status_code,
                    "error_message": error_message,
                    "error_type": error_type,
                    "content": content or None,
                    "content_raw": raw_content if include_raw_content else None,
                    "content_excerpt": content_excerpt,
                    "content_truncated": content_truncated,
                    "title": meta.get("title"),
                    "meta_description": meta.get("meta_description"),
                    "content_length": len(content) if content else 0,
                    "content_hash": _hash_content(content),
                    "links_internal_count": len(internal_links),
                    "links_external_count": len(external_links),
                    "extracted_at": datetime.now(UTC).isoformat(),
                    "retry_attempt": attempt,
                    "will_retry": will_retry,
                }

                if processed_requests >= max_pages:
                    break

                if current_depth < max_depth and success:
                    for link in links.get("internal", []):
                        href = None
                        if isinstance(link, str):
                            href = link
                        elif isinstance(link, dict):
                            href = link.get("href")
                        if not href or href in seen:
                            continue
                        if same_domain_only and base_domains:
                            if urlparse(href).netloc not in base_domains:
                                continue
                        if include_regexes and not any(
                            regex.search(href) for regex in include_regexes
                        ):
                            continue
                        if exclude_regexes and any(regex.search(href) for regex in exclude_regexes):
                            continue
                        if href not in seen:
                            seen.add(href)
                            next_frontier.append((href, current_depth + 1))

            if next_frontier:
                frontier.extend(next_frontier)

            if max_requests_per_minute > 0:
                window_count += len(batch)
