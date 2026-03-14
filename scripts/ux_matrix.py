from __future__ import annotations

# ruff: noqa: E402, I001

import asyncio
import json
import os
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

# Run only "core" scenarios when UX_MATRIX_GROUP=core (fast, minimal external deps).
UX_MATRIX_GROUP = os.environ.get("UX_MATRIX_GROUP", "").strip().lower()

SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "marketing_home",
        "group": "extended",
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
        "group": "extended",
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
        "group": "core",
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
        "group": "core",
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
        "group": "extended",
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
        "group": "extended",
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
        "group": "core",
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
    {
        "id": "redirect_chain",
        "group": "extended",
        "description": "Redirects should resolve and complete cleanly",
        "timeout_secs": 45,
        "input": {
            "start_urls": ["https://httpbin.org/redirect/2"],
            "extract_mode": "text",
            "max_pages": 1,
            "max_depth": 0,
            "same_domain_only": True,
            "max_retries": 0,
            "request_timeout_secs": 20,
        },
    },
    {
        "id": "redirect_chain_long",
        "group": "hard",
        "description": "Longer redirect chain (optional stress)",
        "timeout_secs": 60,
        "input": {
            "start_urls": ["https://httpbin.org/redirect/3"],
            "extract_mode": "text",
            "max_pages": 1,
            "max_depth": 0,
            "same_domain_only": True,
            "max_retries": 0,
            "request_timeout_secs": 25,
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
        "word_count_threshold": 0,
        "virtual_scroll_selector": None,
        "virtual_scroll_count": 10,
        "wait_until": "domcontentloaded",
        "page_load_wait_secs": 0.0,
        "wait_for_selector": None,
        "wait_for_timeout_secs": 30,
        "css_selector": None,
        "crawl_mode": "full",
        "include_link_urls": False,
    }


async def _run_scenario(scenario: dict[str, Any], timeout_secs: int = 180) -> dict[str, Any]:
    payload = _base_input()
    payload.update(scenario["input"])
    expect_error = bool(scenario.get("expect_error"))
    scenario_timeout_secs = int(scenario.get("timeout_secs") or timeout_secs)

    async def _crawl() -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        agen = crawl_urls(**payload)
        try:
            async for item in agen:
                items.append(item)
                if len(items) >= payload["max_pages"]:
                    break
        finally:
            # Ensure underlying browser/crawler resources are released even when we stop early.
            await agen.aclose()
        return items

    try:
        items = await asyncio.wait_for(_crawl(), timeout=scenario_timeout_secs)
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


def _select_scenarios() -> list[dict[str, Any]]:
    group = UX_MATRIX_GROUP
    if group == "core":
        return [s for s in SCENARIOS if s.get("group") == "core"]
    if group == "extended":
        return [s for s in SCENARIOS if s.get("group") in ("core", "extended")]
    if group == "hard":
        return [s for s in SCENARIOS if s.get("group") == "hard"]
    return list(SCENARIOS)


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    scenarios_to_run = _select_scenarios()
    if UX_MATRIX_GROUP:
        print(f"UX_MATRIX_GROUP={UX_MATRIX_GROUP}: running {len(scenarios_to_run)} scenario(s)")
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "group_filter": UX_MATRIX_GROUP or None,
        "scenarios": [],
    }

    t0 = datetime.now(UTC)
    for scenario in scenarios_to_run:
        result = await _run_scenario(scenario)
        report["scenarios"].append(result)
    elapsed_secs = (datetime.now(UTC) - t0).total_seconds()

    report["elapsed_secs"] = round(elapsed_secs, 1)
    ok = sum(1 for r in report["scenarios"] if r["summary"]["status"] == "ok")
    expected_error = sum(
        1 for r in report["scenarios"] if r["summary"]["status"] == "expected_error"
    )
    failed = sum(
        1 for r in report["scenarios"] if r["summary"]["status"] in ("error", "unexpected_ok")
    )
    report["summary_counts"] = {
        "ok": ok,
        "expected_error": expected_error,
        "failed": failed,
        "total": len(report["scenarios"]),
    }

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
    summary_lines.append("")
    summary_lines.append(
        f"Total: {report['summary_counts']['ok']} ok, "
        f"{report['summary_counts']['expected_error']} expected_error, "
        f"{report['summary_counts']['failed']} failed | "
        f"{report['elapsed_secs']}s"
    )

    Path("scripts/ux_matrix_report.txt").write_text("\n".join(summary_lines), encoding="utf-8")
    print("\n".join(summary_lines))


if __name__ == "__main__":
    asyncio.run(main())
