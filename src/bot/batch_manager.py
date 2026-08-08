"""Mass dork batch manager — parallel processing with throughput tracking."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from loguru import logger

from src.core.fetch_engine import FetchEngine
from src.core.filters import URLFilter
from src.core.parser import YahooSerpsParser
from src.core.proxy_pool import ProxyPool
from src.core.query_builder import YahooQueryBuilder
from src.models.config import BotConfig
from src.utils.tls_rotation import TLSRotator
from src.utils.ua_rotation import UserAgentRotator


@dataclass
class DorkResult:
    """Result of a single dork query processing."""
    dork: str
    urls: list[str] = field(default_factory=list)
    error: str | None = None
    pages_fetched: int = 0


@dataclass
class BatchProgress:
    """Tracks progress of a mass dork batch."""
    total: int = 0
    completed: int = 0
    failed: int = 0
    total_urls: int = 0
    started_at: datetime = field(default_factory=datetime.now)

    @property
    def pct(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100

    @property
    def elapsed_sec(self) -> float:
        return (datetime.now() - self.started_at).total_seconds()

    @property
    def urls_per_sec(self) -> float:
        sec = max(self.elapsed_sec, 0.001)
        return self.total_urls / sec


@dataclass
class ThroughputMetrics:
    """Real-time throughput tracking for max-speed monitoring."""
    requests_sent: int = 0
    requests_succeeded: int = 0
    requests_failed: int = 0
    requests_blocked: int = 0
    urls_collected: int = 0
    start_time: float = field(default_factory=time.monotonic)

    @property
    def req_per_sec(self) -> float:
        elapsed = max(time.monotonic() - self.start_time, 0.001)
        return self.requests_sent / elapsed

    @property
    def urls_per_sec(self) -> float:
        elapsed = max(time.monotonic() - self.start_time, 0.001)
        return self.urls_collected / elapsed

    @property
    def success_rate(self) -> float:
        if self.requests_sent == 0:
            return 0.0
        return self.requests_succeeded / self.requests_sent


class BatchManager:
    """High-throughput mass dork processor — streaming pipeline, max speed.

    Processes up to 500 dorks in parallel. Each dork fetches up to 60 pages.
    Global deduplication across all dork results.
    """

    MAX_DORKS = 500

    def __init__(
        self,
        config: BotConfig,
        proxy_pool: ProxyPool,
        tls_rotator: TLSRotator,
        ua_rotator: UserAgentRotator,
        url_filter: URLFilter,
    ) -> None:
        self.config = config
        self.query_builder = YahooQueryBuilder()
        self.proxy_pool = proxy_pool
        self.tls = tls_rotator
        self.ua = ua_rotator
        self.filter = url_filter

    def parse_dork_file(self, content: str) -> list[str]:
        """Parse uploaded .txt content into a clean dork list.

        - Skips blank lines and comments (#)
        - Truncates at MAX_DORKS
        """
        dorks: list[str] = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            dorks.append(line)
        if len(dorks) > self.MAX_DORKS:
            logger.warning(
                f"Dork list truncated: {len(dorks)} > {self.MAX_DORKS}"
            )
            dorks = dorks[: self.MAX_DORKS]
        return dorks

    async def process_batch(
        self,
        dorks: list[str],
        send_progress: Callable | None = None,
        pages_override: int | None = None,
    ) -> tuple[list[str], BatchProgress]:
        """Process all dorks at maximum throughput. No rate limiting.

        Args:
            dorks: List of dork query strings.
            send_progress: Optional async callback(progress, metrics) for updates.
            pages_override: Override pages per dork (1-60).

        Returns:
            Tuple of (aggregated_unique_urls, progress).
        """
        progress = BatchProgress(total=len(dorks))
        metrics = ThroughputMetrics()
        pages = pages_override if pages_override else self.config.max_pages
        pages = max(1, min(60, pages))

        engine = FetchEngine(
            self.proxy_pool,
            self.tls,
            self.ua,
            max_concurrency=self.config.max_concurrency,
            timeout=self.config.request_timeout,
            rate_limit_per_sec=self.config.rate_limit_per_sec,  # 0 = unlimited
        )

        # Limit how many dorks run concurrently
        dork_sem = asyncio.Semaphore(self.config.max_dork_concurrency)

        async def process_one(dork: str) -> DorkResult:
            async with dork_sem:
                try:
                    urls = self.query_builder.build(dork, pages=pages)
                    pages_html = await engine.fetch_all(urls)
                    valid = [h for h in pages_html if h is not None]

                    metrics.requests_sent += len(urls)
                    metrics.requests_succeeded += len(valid)

                    all_urls: list[str] = []
                    for html in valid:
                        all_urls.extend(YahooSerpsParser.parse(html))

                    clean = self.filter.filter(all_urls)
                    metrics.urls_collected += len(clean)

                    result = DorkResult(
                        dork=dork, urls=clean, pages_fetched=len(valid)
                    )
                    progress.completed += 1
                    progress.total_urls += len(clean)

                    # Progress update every 10 dorks
                    if send_progress and progress.completed % 10 == 0:
                        try:
                            await send_progress(progress, metrics)
                        except Exception:
                            pass

                    return result

                except Exception as e:
                    logger.error(f"Dork failed '{dork}': {e}")
                    progress.failed += 1
                    metrics.requests_failed += 1
                    return DorkResult(dork=dork, error=str(e))

        results = await asyncio.gather(*[process_one(d) for d in dorks])

        # Global deduplication across all dorks
        seen: set[str] = set()
        aggregated: list[str] = []
        for r in results:
            for url in r.urls:
                if url not in seen:
                    seen.add(url)
                    aggregated.append(url)

        await engine.close()
        return aggregated, progress

    @staticmethod
    def export_to_file(
        urls: list[str], output_path: str = "output/results.txt"
    ) -> str:
        """Write clean URLs to a .txt file for Telegram document delivery.

        Returns the path to the written file.
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for url in urls:
                f.write(url + "\n")
        return output_path
