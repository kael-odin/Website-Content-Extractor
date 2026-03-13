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
  "maxResults": 1000
}
```

## Output fields

- `url`
- `success`
- `status_code`
- `error_message`
- `content`
