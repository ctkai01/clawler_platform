from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

import httpx

# Ported from opencrawler's crawlers/http_client.py (sync requests.Session
# version) — same per-host min-delay contract, adapted to httpx.AsyncClient
# since this platform's parsers are async throughout. Without a per-host
# delay, Vietnamese news/forum sites 429 or connection-drop after a burst of
# requests (confirmed live against vnexpress.net during development).
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MIN_DELAY = 1.0


class RateLimitedFetcher:
    """Sequential async HTTP GET with a per-host minimum delay between
    requests. One instance per SiteParser call site (not shared across
    hosts) keeps the per-host delay tracking simple."""

    def __init__(
        self,
        min_delay_seconds: float = DEFAULT_MIN_DELAY,
        timeout_seconds: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._min_delay = min_delay_seconds
        self._timeout = timeout_seconds
        self._headers = {"User-Agent": user_agent}
        self._last_at: dict[str, float] = {}

    async def fetch(self, url: str) -> str:
        host = urlparse(url).netloc
        last = self._last_at.get(host, 0.0)
        wait = self._min_delay - (time.monotonic() - last)
        if wait > 0:
            await asyncio.sleep(wait)

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=self._timeout, headers=self._headers
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text
        finally:
            self._last_at[host] = time.monotonic()
