"""High-throughput weighted proxy pool with continuous health probing."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from loguru import logger


@dataclass
class ProxyEntry:
    """Single proxy entry with health and performance tracking."""
    proxy: str
    healthy: bool = True
    failures: int = 0
    successes: int = 0
    last_checked: float = 0.0
    latency_ms: float = 0.0

    @property
    def score(self) -> float:
        """Weighted score: success_rate * (1 / latency). Higher = better."""
        total = self.successes + self.failures
        if total == 0:
            return 0.0
        success_rate = self.successes / total
        latency_penalty = 1.0 / (self.latency_ms + 1)
        return success_rate * latency_penalty


class ProxyPool:
    """High-throughput proxy pool with weighted scoring and background health probing.

    Proxies are scored by success_rate × (1/latency). Best proxies are used most.
    Dead proxies are auto-evicted after max_failures consecutive failures.
    Background task continuously re-probes dead proxies every recheck_interval seconds.
    """

    def __init__(
        self,
        path: str = "data/proxies.txt",
        max_failures: int = 3,
        recheck_interval: int = 30,
    ) -> None:
        self._raw = self._load(path)
        self._entries: list[ProxyEntry] = [ProxyEntry(proxy=p) for p in self._raw]
        self._healthy: list[ProxyEntry] = []
        self._idx = 0
        self._max_failures = max_failures
        self._recheck_interval = recheck_interval
        self._lock = asyncio.Lock()
        self._bg_task: asyncio.Task | None = None

    def _load(self, path: str) -> list[str]:
        """Load proxies from file. One per line: ip:port or ip:port:user:pass."""
        p = Path(path)
        if not p.exists():
            logger.warning(f"Proxy file {path} not found — running direct (no proxy)")
            return []
        return [
            line.strip()
            for line in p.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]

    async def health_check(self) -> None:
        """Initial concurrent health check of all proxies. 50 at a time."""
        if not self._raw:
            return

        sem = asyncio.Semaphore(50)

        async def check(entry: ProxyEntry) -> ProxyEntry | None:
            async with sem:
                proxy_url = self._format_proxy(entry.proxy)
                if not proxy_url:
                    return None
                start = time.monotonic()
                try:
                    async with httpx.AsyncClient(proxy=proxy_url, timeout=5) as c:
                        r = await c.get("https://httpbin.org/ip")
                        if r.status_code == 200:
                            entry.healthy = True
                            entry.successes += 1
                            entry.latency_ms = (time.monotonic() - start) * 1000
                            entry.last_checked = time.time()
                            return entry
                except Exception:
                    entry.healthy = False
                    entry.failures += 1
                    return None

        results = await asyncio.gather(*[check(e) for e in self._entries])
        self._healthy = sorted(
            [e for e in results if e is not None],
            key=lambda e: e.score,
            reverse=True,
        )
        logger.info(
            f"Proxy pool: {len(self._healthy)}/{len(self._raw)} healthy"
        )

    async def _continuous_health_probe(self) -> None:
        """Background task: recheck dead proxies + refresh scores periodically."""
        while True:
            await asyncio.sleep(self._recheck_interval)
            dead = [e for e in self._entries if not e.healthy]
            if not dead:
                continue

            sem = asyncio.Semaphore(50)

            async def recheck(entry: ProxyEntry) -> None:
                async with sem:
                    proxy_url = self._format_proxy(entry.proxy)
                    if not proxy_url:
                        return
                    start = time.monotonic()
                    try:
                        async with httpx.AsyncClient(proxy=proxy_url, timeout=5) as c:
                            r = await c.get("https://httpbin.org/ip")
                            if r.status_code == 200:
                                entry.healthy = True
                                entry.failures = max(0, entry.failures - 1)
                                entry.successes += 1
                                entry.latency_ms = (time.monotonic() - start) * 1000
                    except Exception:
                        pass

            await asyncio.gather(*[recheck(e) for e in dead])
            self._healthy = sorted(
                [e for e in self._entries if e.healthy],
                key=lambda e: e.score,
                reverse=True,
            )
            logger.debug(
                f"Health re-probe: {len(self._healthy)} healthy"
            )

    def start_background_probing(self) -> None:
        """Start continuous health probing in background."""
        if self._bg_task is None:
            self._bg_task = asyncio.create_task(self._continuous_health_probe())

    def stop_background_probing(self) -> None:
        """Stop background health probing."""
        if self._bg_task is not None:
            self._bg_task.cancel()
            self._bg_task = None

    def _format_proxy(self, proxy: str) -> str:
        """Convert ip:port or ip:port:user:pass to http proxy URL."""
        parts = proxy.split(":")
        if len(parts) == 2:
            return f"http://{proxy}"
        elif len(parts) == 4:
            return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        return ""

    async def next(self) -> str | None:
        """Get next healthy proxy (weighted round-robin by score).

        Returns:
            Proxy string (ip:port or ip:port:user:pass), or None for direct.
        """
        async with self._lock:
            if not self._healthy:
                return None
            entry = self._healthy[self._idx % len(self._healthy)]
            self._idx += 1
            return entry.proxy

    def mark_success(self, proxy: str) -> None:
        """Mark a proxy as successful (call after good response)."""
        for e in self._entries:
            if e.proxy == proxy:
                e.successes += 1
                e.healthy = True
                return

    def mark_failure(self, proxy: str) -> None:
        """Mark a proxy as failed. Evict after max_failures."""
        for e in self._entries:
            if e.proxy == proxy:
                e.failures += 1
                if e.failures >= self._max_failures:
                    e.healthy = False
                    self._healthy = [h for h in self._healthy if h.proxy != proxy]
                    logger.debug(
                        f"Proxy evicted: {proxy} ({e.failures} failures)"
                    )
                return

    @property
    def count(self) -> int:
        """Number of currently healthy proxies."""
        return len(self._healthy)

    @property
    def total(self) -> int:
        """Total number of proxies loaded (healthy + dead)."""
        return len(self._raw)
