"""Yahoo SERP HTML parser — extract organic result URLs from search pages."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse
from loguru import logger


class YahooSerpsParser(HTMLParser):
    """Parse Yahoo SERP HTML and extract organic result URLs.

    Yahoo wraps result URLs in redirect links like:
        r.search.yahoo.com/_ylt=.../RU=<actual-url>/RK=...
    This parser extracts the real URL from the redirect wrapper
    and also handles direct links.
    """

    # Yahoo redirect pattern: /RU=<url-encoded-actual-url>/RK=
    REDIRECT_PATTERN = re.compile(r"/RU=([^/]+)/RK=")
    # Alternative redirect pattern (some Yahoo layouts)
    REDIRECT_PATTERN_ALT = re.compile(r"RU=([^/&]+)")

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for attr, val in attrs:
                if attr == "href" and val:
                    self._extract_url(val)

    def _extract_url(self, href: str) -> None:
        """Extract the real URL from a Yahoo result href."""
        # Try primary redirect pattern
        m = self.REDIRECT_PATTERN.search(href)
        if m:
            actual = unquote(m.group(1))
            if self._is_valid_url(actual):
                self.urls.append(actual)
            return

        # Try alternative redirect pattern
        m = self.REDIRECT_PATTERN_ALT.search(href)
        if m:
            actual = unquote(m.group(1))
            if self._is_valid_url(actual):
                self.urls.append(actual)
            return

        # Direct link — skip Yahoo internal links
        if "yahoo.com" in href or "search.yahoo" in href:
            return
        if self._is_valid_url(href):
            self.urls.append(href)

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Check if URL is a valid http(s) URL with a netloc."""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ("http", "https") and bool(parsed.netloc)
        except Exception:
            return False

    @classmethod
    def parse(cls, html: str) -> list[str]:
        """Parse Yahoo SERP HTML and return deduplicated list of URLs.

        Args:
            html: Raw Yahoo search result page HTML.

        Returns:
            Deduplicated list of result URLs (preserving order).
        """
        parser = cls()
        try:
            parser.feed(html)
        except Exception as e:
            logger.debug(f"HTML parse error: {e}")
        # Deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for u in parser.urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        return unique
