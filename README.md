# Crawl4AI Web Crawler Actor

Apify Actor wrapper around the open-source crawl4ai project.

## Local dev

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -U pip
pip install -e ".[dev]"
crawl4ai-setup
python -m crawl4ai_actor.main
```

## Notes

- The actor expects input via Apify's input schema.
- Outputs are stored in the default dataset.

## UX smoke test

```bash
.venv/Scripts/python scripts/ux_smoke.py
```

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
  "userAgent": null
}
```

## Output fields

- `url`
- `success`
- `status_code`
- `error_message`
- `error_type`
- `content`
- `title`
- `meta_description`
- `content_length`
- `content_hash`
- `links_internal_count`
- `links_external_count`
- `extracted_at`
- `retry_attempt`
- `will_retry`
