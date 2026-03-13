from __future__ import annotations

import asyncio

from apify import Actor

from crawl4ai_actor.config import ActorInput
from crawl4ai_actor.crawler import crawl_urls


async def _run() -> None:
    async with Actor:
        raw_input = await Actor.get_input() or {}
        actor_input = ActorInput(**raw_input)

        proxy_url: str | None = None
        if actor_input.use_proxy:
            proxy_url = await _maybe_get_proxy_url(actor_input.proxy_groups)

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
        ):
            await Actor.push_data(item)
            processed += 1
            if processed >= actor_input.max_results:
                break


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
