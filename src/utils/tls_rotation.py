"""TLS fingerprint rotation using curl_cffi browser impersonation."""

from __future__ import annotations

import random
from loguru import logger

# curl_cffi supports impersonating these browser profiles.
# Each profile produces a unique JA3/JA4 fingerprint + HTTP/2 settings.
IMPERSONATE_PROFILES: list[str] = [
    "chrome120", "chrome119", "chrome116", "chrome110",
    "chrome107", "chrome104", "chrome101", "chrome100",
    "edge101", "edge99",
    "safari17_0", "safari15_3", "safari15_2",
    "firefox120", "firefox117",
]


class TLSRotator:
    """Rotate TLS fingerprint profiles for curl_cffi impersonation."""

    def __init__(self, profiles: list[str] | None = None) -> None:
        self._profiles = list(profiles) if profiles else list(IMPERSONATE_PROFILES)
        self._idx = 0

    def next_profile(self) -> str:
        """Round-robin TLS profile."""
        p = self._profiles[self._idx % len(self._profiles)]
        self._idx += 1
        return p

    def random_profile(self) -> str:
        """Random TLS profile (for retry rotation)."""
        return random.choice(self._profiles)

    def create_session(self, proxy: str | None = None):
        """Create a curl_cffi AsyncSession with a rotated TLS fingerprint.

        Args:
            proxy: proxy URL (e.g., 'http://ip:port' or None for direct)

        Returns:
            curl_cffi.requests.AsyncSession configured with impersonation.
        """
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError:
            logger.error("curl_cffi not installed — cannot create TLS session")
            raise

        profile = self.next_profile()
        kwargs: dict = {"impersonate": profile}
        if proxy:
            kwargs["proxies"] = {"https": proxy, "http": proxy}
        return AsyncSession(**kwargs)

    @property
    def count(self) -> int:
        return len(self._profiles)
