from __future__ import annotations

# ruff: noqa: E402, I001

import asyncio
import json
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

warnings.filterwarnings(
    "ignore",
    message=(
        r"urllib3 \(.+\) or chardet \(.+\)/charset_normalizer \(.+\) "
        r"doesn't match a supported version!"
    ),
)

from crawl4ai_actor.crawler import crawl_urls


SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "marketing_home",
        "description": "Marketing homepage with dynamic content",
        "input": {
            "start_urls": ["https://www.apify.com"],
            "extract_mode": "markdown",
            "max_pages": 3,
            "max_depth": 1,
        },
    },
    {
        "id": "knowledge_base",
        "description": "Static knowledge page",
        "input": {
            "start_urls": ["https://www.wikipedia.org"],
            "extract_mode": "markdown",
            "max_pages": 3,
            "max_depth": 1,
        },
    },
    {
        "id": "simple_static",
        "description": "Small static site",
        "input": {
            "start_urls": ["https://example.com"],
            "extract_mode": "text",
            "max_pages": 1,
            "max_depth": 0,
        },
    },
    {
        "id": "mixed_start_urls",
        "description": "Mixed valid/invalid start URLs (normalization + filtering)",
        "input": {
            "start_urls": [
                " https://EXAMPLE.com#section ",
                "mailto:test@example.com",
                "javascript:alert(1)",
                "/relative/path",
            ],
            "extract_mode": "text",
            "max_pages": 1,
            "max_depth": 0,
        },
    },
    {
        "id": "developer_docs",
        "description": "Docs site with deep nav",
        "input": {
            "start_urls": ["https://docs.apify.com/"],
            "extract_mode": "markdown",
            "max_pages": 3,
            "max_depth": 1,
        },
    },
    {
        "id": "blog",
        "description": "Blog with mixed content",
        "input": {
            "start_urls": ["https://blog.apify.com/"],
            "extract_mode": "markdown",
            "max_pages": 3,
            "max_depth": 1,
            "include_patterns": [r"/20"],
        },
    },
    {
        "id": "invalid_regex_patterns",
        "description": "Invalid regex patterns should fail fast with clear error",
        "expect_error": True,
        "input": {
            "start_urls": ["https://example.com"],
            "extract_mode": "text",
            "max_pages": 1,
            "max_depth": 0,
            "include_patterns": ["("],
        },
    },
]


def _base_input() -> dict[str, Any]:
    return {
        "max_pages": 3,
        "max_depth": 1,
        "concurrency": 2,
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
        "clean_content": True,
        "include_raw_content": False,
        "max_content_chars": 5000,
        "content_excerpt_chars": 200,
    }


async def _run_scenario(scenario: dict[str, Any], timeout_secs: int = 180) -> dict[str, Any]:
    payload = _base_input()
    payload.update(scenario["input"])
    expect_error = bool(scenario.get("expect_error"))

    async def _crawl() -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        async for item in crawl_urls(**payload):
            items.append(item)
            if len(items) >= payload["max_pages"]:
                break
        return items

    try:
        items = await asyncio.wait_for(_crawl(), timeout=timeout_secs)
        status = "ok"
        error = None
    except Exception as exc:  # noqa: BLE001
        items = []
        status = "expected_error" if expect_error else "error"
        error = f"{type(exc).__name__}: {exc}"
    else:
        if expect_error:
            status = "unexpected_ok"

    summary = {
        "id": scenario["id"],
        "description": scenario["description"],
        "status": status,
        "error": error,
        "count": len(items),
        "success": sum(1 for item in items if item.get("success")),
        "avg_content_length": int(
            sum((item.get("content_length", 0) or 0) for item in items) / len(items)
        )
        if items
        else 0,
        "errors": {},
        "sample_urls": [item.get("url") for item in items[:3]],
    }

    for item in items:
        key = item.get("error_type") or "none"
        summary["errors"][key] = summary["errors"].get(key, 0) + 1

    return {
        "scenario": scenario,
        "summary": summary,
        "items": items,
    }


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scenarios": [],
    }

    for scenario in SCENARIOS:
        result = await _run_scenario(scenario)
        report["scenarios"].append(result)

    output_path = Path("scripts/ux_matrix_output.json")
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_lines = ["UX MATRIX SUMMARY"]
    for scenario in report["scenarios"]:
        summary = scenario["summary"]
        summary_lines.append(
            f"- {summary['id']}: {summary['status']} | "
            f"{summary['success']}/{summary['count']} success | "
            f"avg_len={summary['avg_content_length']}"
        )

    Path("scripts/ux_matrix_report.txt").write_text(
        "\n".join(summary_lines), encoding="utf-8"
    )
    print("\n".join(summary_lines))


if __name__ == "__main__":
    asyncio.run(main())
