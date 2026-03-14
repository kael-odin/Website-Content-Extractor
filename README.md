# Website Content Extractor

Extract clean website content, page metadata, and link statistics into a structured dataset. Designed for content audits, monitoring, indexing, and data pipelines.

## Features

- Extract page content in markdown, HTML, or text.
- Capture title, meta description, content length, and link counts.
- Filter by domain, include/exclude URL patterns, and set crawl depth.
- Built-in retry, backoff, and rate limiting for stability.
- Output schema ready for dataset views.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -U pip
pip install -e ".[dev]"
crawl4ai-setup
python -m crawl4ai_actor.main
```

## How it works

1. Provide one or more start URLs.
2. The actor crawls within your depth and rate limits.
3. Results are written to the default dataset, with content and metadata ready to use.

## Input example

```json
{
  "startUrls": ["https://example.com"],
  "maxPages": 50,
  "maxDepth": 2,
  "concurrency": 5,
  "requestTimeoutSecs": 60,
  "headless": true,
  "useProxy": false,
  "extractMode": "markdown",
  "maxResults": 1000,
  "sameDomainOnly": true,
  "includePatterns": [],
  "excludePatterns": [],
  "maxRetries": 2,
  "retryBackoffSecs": 2,
  "maxRequestsPerMinute": 0,
  "enableStealth": false,
  "userAgent": null,
  "cleanContent": true,
  "includeRawContent": false,
  "maxContentChars": 0,
  "contentExcerptChars": 300
}
```

## Input reference

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `startUrls` | array | required | Starting URLs to visit. |
| `maxPages` | integer | 50 | Maximum pages to process. |
| `maxDepth` | integer | 2 | Maximum link depth from each start URL. |
| `concurrency` | integer | 5 | Number of concurrent tasks. |
| `requestTimeoutSecs` | integer | 60 | Timeout per page request. |
| `headless` | boolean | true | Run browser headless. |
| `useProxy` | boolean | false | Enable Apify proxy. |
| `proxyGroups` | array | null | Proxy groups to use when proxy is enabled. |
| `extractMode` | string | markdown | Output format: markdown, html, or text. |
| `maxResults` | integer | 1000 | Maximum output items to push. |
| `sameDomainOnly` | boolean | true | Only follow links within start URL domains. |
| `includePatterns` | array | [] | Regex patterns to include URLs. |
| `excludePatterns` | array | [] | Regex patterns to exclude URLs. |
| `maxRetries` | integer | 2 | Retry failed pages. |
| `retryBackoffSecs` | integer | 2 | Base retry backoff in seconds. |
| `maxRequestsPerMinute` | integer | 0 | Global rate limit (0 = unlimited). |
| `enableStealth` | boolean | false | Enable stealth mode for tougher sites. |
| `userAgent` | string | null | Override the user agent string. |
| `cleanContent` | boolean | true | Remove navigation-heavy lines and normalize whitespace. |
| `includeRawContent` | boolean | false | Include unmodified content output. |
| `maxContentChars` | integer | 0 | Truncate content length (0 = unlimited). |
| `contentExcerptChars` | integer | 300 | Content excerpt length for previews. |

## Output schema

Each dataset item includes:

- `url` (string)
- `success` (boolean)
- `status_code` (integer or null)
- `error_message` (string or null)
- `error_type` (string or null)
- `content` (string or null)
- `content_raw` (string or null)
- `content_excerpt` (string or null)
- `content_truncated` (boolean)
- `title` (string or null)
- `meta_description` (string or null)
- `content_length` (integer)
- `content_hash` (string or null)
- `links_internal_count` (integer)
- `links_external_count` (integer)
- `extracted_at` (ISO timestamp)
- `retry_attempt` (integer)
- `will_retry` (boolean)

## Dataset view

The dataset view is defined in `.actor/dataset_schema.json` and linked from `.actor/output_schema.json`.

## Docker

```bash
docker build -t website-content-extractor .
```

## UX regression (matrix)

Multi-scenario regression over real sites and edge cases (redirects, mixed URLs, invalid regex). Reports to `scripts/ux_matrix_output.json` and `scripts/ux_matrix_report.txt`.

```bash
python scripts/ux_matrix.py
```

Fast run (core only: example.com, mixed URLs, invalid regex; no external marketing/docs sites):

```bash
UX_MATRIX_GROUP=core python scripts/ux_matrix.py
```
