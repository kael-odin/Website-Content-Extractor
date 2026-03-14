# Website Content Extractor

CafeScraper Worker: crawls one or more start URLs, extracts page content (markdown, HTML, or text), metadata, and link stats. Uses [crawl4ai](https://github.com/unclecode/crawl4ai) for browser-based extraction.

## Quick start (CafeScraper Worker)

- **Entry point:** `main.py` (root). The platform runs this and communicates via gRPC (`127.0.0.1:20086`).
- **Input:** Defined in `input_schema.json` (CafeScraper format). Required: `startUrls`. Optional: `maxPages`, `maxDepth`, `extractMode`, `crawlMode`, etc.
- **Output:** Each crawled page is pushed as one row: `url`, `success`, `status_code`, `content`, `title`, `content_excerpt`, `content_length`, `links_internal_count`, `links_external_count`, `extracted_at`, and more.

```bash
pip install -r requirements.txt
crawl4ai-setup
python main.py
```

When run on CafeScraper, the platform injects input via the SDK and optional proxy via `PROXY_AUTH`. Set **Use proxy** in the input (or rely on platform defaults) to use the injected proxy.

## Input (main fields)

| Field | Description |
|-------|-------------|
| `startUrls` | Starting URLs to crawl (required). |
| `maxPages` | Max pages to process (default 50). |
| `maxDepth` | Max link depth from start URLs (default 2). |
| `extractMode` | `markdown` \| `html` \| `text`. |
| `crawlMode` | `full` (extract content) \| `discover_only` (URLs and links only). |
| `waitUntil` | `domcontentloaded` \| `load` \| `networkidle`. |
| `waitForSelector` | CSS selector to wait for before extraction. |
| `cssSelector` | Extract only content inside this selector. |

**Example (SPA / slow site):** `startUrls: ["https://..."], waitUntil: "networkidle", pageLoadWaitSecs: 2`  
**Example (discover links only):** `startUrls: ["https://..."], crawlMode: "discover_only", maxPages: 100`

## Project layout

- `main.py` — CafeScraper worker entry: reads input via SDK, runs crawler, pushes results.
- `input_schema.json` — CafeScraper input form (description, `b`, `properties`).
- `sdk.py`, `sdk_pb2.py`, `sdk_pb2_grpc.py` — CafeScraper gRPC SDK.
- `src/crawl4ai_actor/` — Crawl logic: `config.py` (input model), `crawler.py` (crawl4ai crawl loop).
- `requirements.txt` — Python deps (crawl4ai, pydantic, grpcio, protobuf).

## Browser

The worker uses crawl4ai’s built-in browser (Playwright). The run environment must have Chromium available (e.g. `playwright install chromium` or an image with Chromium). Proxy is applied when the platform sets `PROXY_AUTH`.

## Local / dev

- Run the worker locally: ensure the CafeScraper runtime is present (gRPC server on `127.0.0.1:20086`), or mock input and call the crawler directly.
- Run the original Apify-style actor (if you keep it): `python -m crawl4ai_actor.main` with Apify storage and input.
