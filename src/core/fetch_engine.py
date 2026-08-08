"""High-throughput parallel fetch engine — no rate limiter, instant retry on block."""

from __future__ import annotations

import asyncio
import time
from typing import AsyncGenerator

from loguru import logger

from src.core.proxy_pool import ProxyPool
from src.utils.tls_rotation import TLSRotator
from src.utils.ua_rotation import UserAgentRotator

# Block-detection status codes
BLOCK_STATUSES: frozenset[int] = frozenset({429, 403, 503})


class FetchEngine:
    """High-throughput fetch engine for Yahoo SERP pages.

    Features:
    - No rate limiter (rate_limit_per_sec=0 = unlimited)
    - Instant retry on block (429/403/503) with new identity
    - Proxy feedback (mark_success / mark_failure)
    - Streaming results via fetch_stream() for real-time pipeline
    """

    def __init__(
        self,
        proxy_pool: ProxyPool,
        tls_rotator: TLSRotator,
        ua_rotator: UserAgentRotator,
        max_concurrency: int = 300,
        timeout: int = 10,
        rate_limit_per_sec: float = 0.0,
        max_retries: int = 2,
    ) -> None:
        self._proxy = proxy_pool
        self._tls = tls_rotator
        self._ua = ua_rotator
        self._sem = asyncio.Semaphore(max_concurrency)
        self._timeout = timeout
        self._max_retries = max_retries
        self._rate_limit = rate_limit_per_sec
        self._last_request = 0.0

    async def fetch(self, url: str) -> str | None:
        """Fetch a single URL with full identity rotation + instant retry on block.

        Returns HTML string on success, None on failure.
        """
        async with self._sem:
            if self._rate_limit > 0:
                await self._rate_limit_wait()
            return await self._fetch_with_retry(url)

    async def _fetch_with_retry(self, url: str) -> str | None:
        """Fetch with instant retry — rotate identity on any failure."""
        for attempt in range(self._max_retries + 1):
            proxy = await self._proxy.next()
            ua = self._ua.next()
            session = self._tls.create_session(proxy=proxy)

            headers = {
                "User-Agent": ua,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://search.yahoo.com/",
                "Connection": "keep-alive",
            }

            try:
                r = await session.get(
                    url,
                    headers=headers,
                    timeout=self._timeout,
                    allow_redirects=True,
                )

                if r.status_code == 200:
                    if proxy:
                        self._proxy.mark_success(proxy)
                    await session.close()
                    return r.text

                # Block detection — 429, 403, 503 = WAF/CAPTCHA/rate-limit
                if r.status_code in BLOCK_STATUSES:
                    logger.debug(
                        f"Block {r.status_code} on {url} "
                        f"(attempt {attempt + 1})"
                    )
                    if proxy:
                        self._proxy.mark_failure(proxy)
                    await session.close()
                    continue  # instant retry with new identity

                # Other non-200 — proxy worked, just not what we expected
                logger.debug(f"Fetch {url}: status {r.status_code}")
                if proxy:
                    self._proxy.mark_success(proxy)
                await session.close()
                return None

            except Exception as e:
                logger.debug(
                    f"Fetch {url}: {type(e).__name__}: {e} "
                    f"(attempt {attempt + 1})"
                )
                if proxy:
                    self._proxy.mark_failure(proxy)
                try:
                    await session.close()
                except Exception:
                    pass
                continue  # retry with new identity

        return None

    async def fetch_all(self, urls: list[str]) -> list[str | None]:
        """Fetch all URLs in parallel — no rate limit, max throughput.

        Returns list of results (str or None) in same order as input URLs.
        """
        return await asyncio.gather(*[self.fetch(u) for u in urls])

    async def fetch_stream(self, urls: list[str]) -> AsyncGenerator[str | None, None]:
        """Stream results as they complete (for real-time output pipeline).

        Yields HTML strings (or None) as each fetch completes.
        Order is NOT guaranteed — results arrive as they finish.
        """
        tasks = [asyncio.create_task(self.fetch(u)) for u in urls]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            yield result

    async def _rate_limit_wait(self) -> None:
        """Wait if rate limiter is active (rate_limit_per_sec > 0)."""
        now = time.monotonic()
        elapsed = now - self._last_request
        min_interval = 1.0 / self._rate_limit
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self._last_request = time.monotonic()

    async def close(self) -> None:
        """Clean up resources."""
        pass  # sessions are created/closed per-request for identity isolation
