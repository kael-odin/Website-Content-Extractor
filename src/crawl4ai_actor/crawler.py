from __future__ import annotations

import hashlib
import re
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
) -> AsyncIterator[dict]:
    browser_config = BrowserConfig(
        headless=headless,
        proxy=proxy_url,
    )
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
        for url in start_urls:
            if url not in seen:
                seen.add(url)
                frontier.append((url, 0))

        processed = 0
        while frontier and processed < max_pages:
            current_depth = frontier[0][1]
            if current_depth > max_depth:
                break

            batch: list[str] = []
            next_frontier: list[tuple[str, int]] = []

            remaining = max_pages - processed
            while frontier and frontier[0][1] == current_depth and len(batch) < remaining:
                url, depth = frontier.pop(0)
                if depth != current_depth:
                    frontier.insert(0, (url, depth))
                    break
                batch.append(url)

            async for result in _iter_results(crawler, batch, run_config):
                processed += 1
                content = _extract_content(result, extract_mode)
                meta = _extract_metadata(result)
                links = getattr(result, "links", {}) or {}
                internal_links = links.get("internal", []) if isinstance(links, dict) else []
                external_links = links.get("external", []) if isinstance(links, dict) else []
                yield {
                    "url": getattr(result, "url", None),
                    "success": getattr(result, "success", None),
                    "status_code": getattr(result, "status_code", None),
                    "error_message": getattr(result, "error_message", None),
                    "content": content,
                    "title": meta.get("title"),
                    "meta_description": meta.get("meta_description"),
                    "content_length": len(content) if content else 0,
                    "content_hash": _hash_content(content),
                    "links_internal_count": len(internal_links),
                    "links_external_count": len(external_links),
                    "extracted_at": datetime.now(UTC).isoformat(),
                }

                if processed >= max_pages:
                    break

                if current_depth < max_depth and getattr(result, "success", False):
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
