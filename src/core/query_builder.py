"""Yahoo search URL construction with pagination support."""

from __future__ import annotations

from urllib.parse import quote_plus


class YahooQueryBuilder:
    """Build paginated Yahoo search URLs from dork queries."""

    BASE_URL = "https://search.yahoo.com/search"

    def build(self, dork: str, pages: int = 10) -> list[str]:
        """Build paginated Yahoo search URLs for a dork query.

        Args:
            dork: Yahoo dork query string (e.g., 'site:example.com "gift card"')
            pages: Number of result pages to fetch (1-60)

        Returns:
            List of Yahoo search URLs, one per page.
        """
        pages = max(1, min(60, pages))
        urls: list[str] = []
        for page in range(pages):
            # Yahoo uses `b=` parameter for offset (1-indexed, increment by 10)
            offset = page * 10 + 1
            url = f"{self.BASE_URL}?p={quote_plus(dork)}&b={offset}&pz=10"
            urls.append(url)
        return urls

    def build_single(self, dork: str) -> str:
        """Build a single Yahoo search URL (first page only)."""
        return f"{self.BASE_URL}?p={quote_plus(dork)}&pz=10"
