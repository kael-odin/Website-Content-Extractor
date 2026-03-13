from crawl4ai_actor.config import ActorInput


def test_input_aliases() -> None:
    payload = {
        "startUrls": ["https://example.com"],
        "maxPages": 10,
        "maxDepth": 1,
        "concurrency": 3,
        "requestTimeoutSecs": 30,
        "headless": False,
        "useProxy": True,
        "proxyGroups": ["RESIDENTIAL"],
        "extractMode": "markdown",
        "maxResults": 5,
        "sameDomainOnly": False,
        "includePatterns": ["example"],
        "excludePatterns": ["ignore"],
        "maxRetries": 1,
        "retryBackoffSecs": 5,
        "maxRequestsPerMinute": 120,
        "enableStealth": True,
        "userAgent": "UA",
    }
    parsed = ActorInput(**payload)

    assert parsed.start_urls == ["https://example.com"]
    assert parsed.max_pages == 10
    assert parsed.max_depth == 1
    assert parsed.concurrency == 3
    assert parsed.request_timeout_secs == 30
    assert parsed.headless is False
    assert parsed.use_proxy is True
    assert parsed.proxy_groups == ["RESIDENTIAL"]
    assert parsed.extract_mode == "markdown"
    assert parsed.max_results == 5
    assert parsed.same_domain_only is False
    assert parsed.include_patterns == ["example"]
    assert parsed.exclude_patterns == ["ignore"]
    assert parsed.max_retries == 1
    assert parsed.retry_backoff_secs == 5
    assert parsed.max_requests_per_minute == 120
    assert parsed.enable_stealth is True
    assert parsed.user_agent == "UA"
