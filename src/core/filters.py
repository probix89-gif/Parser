"""URL filter pipeline — remove blocklisted domains, bad paths, duplicates."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from loguru import logger


class URLFilter:
    """Multi-stage URL filter: blocklist → subdomain match → path filter → dedup."""

    # Common non-result URL patterns to exclude
    BLOCKED_PATHS: frozenset[str] = frozenset({
        "/search", "/login", "/auth", "/signin",
        "/register", "/signup", "/cart", "/checkout",
        "/account", "/dashboard", "/admin", "/wp-admin",
        "/wp-login", "/reset", "/forgot",
    })

    def __init__(self, blocklist_path: str = "data/blocklist.txt") -> None:
        self.blocked_domains: set[str] = self._load_blocklist(blocklist_path)

    def _load_blocklist(self, path: str) -> set[str]:
        """Load blocklist domains from file. Returns lowercase domain set."""
        p = Path(path)
        if not p.exists():
            logger.warning(f"Blocklist {path} not found — no domains blocked")
            return set()
        return {
            line.strip().lower()
            for line in p.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        }

    def filter(self, urls: list[str]) -> list[str]:
        """Filter URL list: remove blocklisted domains, bad paths, duplicates.

        Args:
            urls: Raw URL list to filter.

        Returns:
            Filtered, deduplicated URL list preserving order.
        """
        result: list[str] = []
        seen: set[str] = set()

        for url in urls:
            # Dedup
            if url in seen:
                continue
            seen.add(url)

            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www. prefix for comparison
            domain_clean = domain.removeprefix("www.")

            # Skip non-http(s)
            if parsed.scheme not in ("http", "https"):
                continue

            # Skip empty domains
            if not domain_clean:
                continue

            # Skip blocklisted domains (exact match)
            if domain_clean in self.blocked_domains:
                continue

            # Skip subdomains of blocked domains
            if any(domain_clean.endswith(f".{b}") for b in self.blocked_domains):
                continue

            # Skip blocked paths
            path_lower = parsed.path.lower()
            if any(path_lower.startswith(bp) for bp in self.BLOCKED_PATHS):
                continue

            result.append(url)

        return result

    @property
    def blocklist_count(self) -> int:
        """Number of blocked domains."""
        return len(self.blocked_domains)
