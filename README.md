# Website Content Extractor

Apify Actor: extract page content (markdown/HTML/text), metadata, and link stats. Uses [crawl4ai](https://github.com/unclecode/crawl4ai).

## Quick start

```bash
pip install -e ".[dev]"
crawl4ai-setup
python -m crawl4ai_actor.main
```

Input: `startUrls` (required), `maxPages`, `maxDepth`, `waitUntil`, `waitForSelector`, `cssSelector`, etc. Full schema: [.actor/input_schema.json](.actor/input_schema.json).

Output: dataset with `url`, `success`, `content`, `title`, `content_length`, `links_internal_count`, etc. Run summary in Storage → Key-value store (`runSummary`).

## Options (high level)

| Option | Purpose |
|--------|--------|
| `waitUntil` | `domcontentloaded` \| `load` \| `networkidle` (SPA/slow sites) |
| `pageLoadWaitSecs` | Extra delay before capture |
| `waitForSelector` | Wait for CSS selector (or `css:`/`js:` prefix) |
| `cssSelector` | Extract only this region (e.g. `main`, `.article`) |
| `virtualScrollSelector` | Infinite-scroll container to expand |

## Run locally / Docker

```bash
docker build -t website-content-extractor .
```

## Regression

```bash
UX_MATRIX_GROUP=core python scripts/ux_matrix.py
```

Reports: `scripts/ux_matrix_output.json`, `scripts/ux_matrix_report.txt` (gitignored).
