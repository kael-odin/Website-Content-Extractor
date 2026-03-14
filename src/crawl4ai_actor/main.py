from __future__ import annotations

# ruff: noqa: E402, I001

import asyncio
import warnings

warnings.filterwarnings(
    "ignore",
    message=(
        r"urllib3 \(.+\) or chardet \(.+\)/charset_normalizer \(.+\) "
        r"doesn't match a supported version!"
    ),
)

from pydantic import ValidationError

from apify import Actor

from crawl4ai_actor.config import ActorInput
from crawl4ai_actor.crawler import crawl_urls


async def _run() -> None:
    async with Actor:
        raw_input = await Actor.get_input() or {}
        if not raw_input or not raw_input.get("startUrls"):
            Actor.log.error(
                "Missing required input: startUrls. Example: {'startUrls': ['https://example.com']}"
            )
            await _set_run_summary(0, 0, {"input": 1}, 0)
            return
        try:
            actor_input = ActorInput(**raw_input)
        except ValidationError as e:
            Actor.log.error(f"Invalid input: {e}")
            await _set_run_summary(0, 0, {"validation_error": 1}, 0)
            return

        proxy_url: str | None = None
        if actor_input.use_proxy:
            proxy_url = await _maybe_get_proxy_url(actor_input.proxy_groups)

        processed = 0
        success_count = 0
        error_counts: dict[str, int] = {}
        total_content_chars = 0
        try:
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
            ):
                await Actor.push_data(item)
                processed += 1
                if item.get("success"):
                    success_count += 1
                et = item.get("error_type") or "none"
                error_counts[et] = error_counts.get(et, 0) + 1
                total_content_chars += item.get("content_length") or 0
                if processed >= actor_input.max_results:
                    break
        except Exception:
            Actor.log.exception("Crawl failed")
            error_counts["crawl_error"] = error_counts.get("crawl_error", 0) + 1
            await _set_run_summary(processed, success_count, error_counts, total_content_chars)
            raise

        await _set_run_summary(processed, success_count, error_counts, total_content_chars)
        Actor.log.info(
            f"Run finished: {success_count}/{processed} pages ok, errors: {dict(error_counts)}"
        )


async def _set_run_summary(
    processed: int,
    success_count: int,
    error_counts: dict[str, int],
    total_content_chars: int,
) -> None:
    run_summary = {
        "totalPages": processed,
        "successCount": success_count,
        "failedCount": processed - success_count,
        "errorTypes": error_counts,
        "totalContentLength": total_content_chars,
    }
    await Actor.set_value("runSummary", run_summary)


async def _maybe_get_proxy_url(proxy_groups: list[str] | None) -> str | None:
    create_proxy = getattr(Actor, "create_proxy_configuration", None)
    if create_proxy is None:
        Actor.log.warning("Apify proxy requested, but SDK proxy helper is unavailable.")
        return None

    proxy_config = create_proxy(groups=proxy_groups)
    if asyncio.iscoroutine(proxy_config):
        proxy_config = await proxy_config

    new_url = getattr(proxy_config, "new_url", None)
    if new_url is None:
        Actor.log.warning("Apify proxy requested, but proxy configuration has no new_url().")
        return None

    proxy_url = new_url()
    if asyncio.iscoroutine(proxy_url):
        proxy_url = await proxy_url
    return proxy_url


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
