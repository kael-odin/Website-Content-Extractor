from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from crawl4ai_actor.crawler import crawl_urls


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    input_payload = {
        "start_urls": ["https://www.thordata.com", "https://www.wikipedia.org"],
        "max_pages": 6,
        "max_depth": 1,
        "concurrency": 3,
        "request_timeout_secs": 60,
        "headless": True,
        "proxy_url": None,
        "extract_mode": "markdown",
        "same_domain_only": True,
        "include_patterns": [],
        "exclude_patterns": [],
        "max_retries": 1,
        "retry_backoff_secs": 2,
        "max_requests_per_minute": 0,
        "enable_stealth": True,
        "user_agent": None,
    }

    results = []
    async for item in crawl_urls(**input_payload):
        results.append(item)
        if len(results) >= 6:
            break

    output_path = Path("scripts/ux_smoke_output.json")
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(results)} results to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
