from __future__ import annotations

from typing import Any, AsyncIterator, Iterable, List, Optional, Set, Tuple

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig


def _extract_content(result: Any, extract_mode: str) -> Optional[str]:
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


async def _iter_results(
    crawler: AsyncWebCrawler,
    urls: List[str],
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
    start_urls: List[str],
    max_pages: int,
    max_depth: int,
    concurrency: int,
    request_timeout_secs: int,
    headless: bool,
    proxy_url: Optional[str],
    extract_mode: str,
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

    async with AsyncWebCrawler(config=browser_config) as crawler:
        seen: Set[str] = set()
        frontier: List[Tuple[str, int]] = []
        for url in start_urls:
            if url not in seen:
                seen.add(url)
                frontier.append((url, 0))

        processed = 0
        while frontier and processed < max_pages:
            current_depth = frontier[0][1]
            if current_depth > max_depth:
                break

            batch: List[str] = []
            next_frontier: List[Tuple[str, int]] = []

            remaining = max_pages - processed
            while frontier and frontier[0][1] == current_depth and len(batch) < remaining:
                url, depth = frontier.pop(0)
                if depth != current_depth:
                    frontier.insert(0, (url, depth))
                    break
                batch.append(url)

            async for result in _iter_results(crawler, batch, run_config):
                processed += 1
                yield {
                    "url": getattr(result, "url", None),
                    "success": getattr(result, "success", None),
                    "status_code": getattr(result, "status_code", None),
                    "error_message": getattr(result, "error_message", None),
                    "content": _extract_content(result, extract_mode),
                }

                if processed >= max_pages:
                    break

                if current_depth < max_depth and getattr(result, "success", False):
                    links = getattr(result, "links", {}) or {}
                    for link in links.get("internal", []):
                        href = None
                        if isinstance(link, str):
                            href = link
                        elif isinstance(link, dict):
                            href = link.get("href")
                        if href and href not in seen:
                            seen.add(href)
                            next_frontier.append((href, current_depth + 1))

            if next_frontier:
                frontier.extend(next_frontier)
