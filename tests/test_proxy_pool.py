"""Tests for ProxyPool."""

import asyncio
import tempfile
import os
from pathlib import Path

from src.core.proxy_pool import ProxyPool, ProxyEntry


PROXY_CONTENT = """# Sample proxies
1.2.3.4:8080
5.6.7.8:3128:user:pass
# comment line
9.10.11.12:8888
"""


class TestProxyPool:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.proxy_path = os.path.join(self.tmpdir, "proxies.txt")
        with open(self.proxy_path, "w") as f:
            f.write(PROXY_CONTENT)
        self.pool = ProxyPool(self.proxy_path, max_failures=3)

    def test_load_proxies(self):
        assert self.pool.total == 3  # 3 non-comment lines

    def test_format_proxy_ip_port(self):
        assert self.pool._format_proxy("1.2.3.4:8080") == "http://1.2.3.4:8080"

    def test_format_proxy_with_auth(self):
        assert (
            self.pool._format_proxy("5.6.7.8:3128:user:pass")
            == "http://user:pass@5.6.7.8:3128"
        )

    def test_format_proxy_invalid(self):
        assert self.pool._format_proxy("invalid") == ""

    def test_next_returns_none_when_empty(self):
        pool = ProxyPool("/nonexistent/path")
        assert asyncio.run(pool.next()) is None

    def test_next_returns_none_before_health_check(self):
        # _healthy is empty before health_check runs
        assert asyncio.run(self.pool.next()) is None

    def test_mark_failure_evicts(self):
        # Simulate manual entry for mark_failure testing
        entry = ProxyEntry(proxy="1.2.3.4:8080")
        self.pool._entries = [entry]
        self.pool._healthy = [entry]

        for _ in range(3):
            self.pool.mark_failure("1.2.3.4:8080")

        assert entry.healthy is False
        assert entry not in self.pool._healthy

    def test_mark_success_restores(self):
        entry = ProxyEntry(proxy="1.2.3.4:8080", healthy=False, failures=2)
        self.pool._entries = [entry]

        self.pool.mark_success("1.2.3.4:8080")

        assert entry.healthy is True
        assert entry.successes == 1

    def test_missing_file_warning(self):
        pool = ProxyPool("/nonexistent/proxies.txt")
        assert pool.total == 0


class TestProxyEntry:
    def test_score_zero_when_no_data(self):
        entry = ProxyEntry(proxy="test")
        assert entry.score == 0.0

    def test_score_increases_with_success(self):
        entry = ProxyEntry(proxy="test", successes=10, failures=0, latency_ms=100)
        assert entry.score > 0

    def test_score_decreases_with_failures(self):
        good = ProxyEntry(proxy="a", successes=9, failures=1, latency_ms=100)
        bad = ProxyEntry(proxy="b", successes=1, failures=9, latency_ms=100)
        assert good.score > bad.score

    def test_score_prefers_faster_proxy(self):
        fast = ProxyEntry(proxy="a", successes=10, failures=0, latency_ms=50)
        slow = ProxyEntry(proxy="b", successes=10, failures=0, latency_ms=500)
        assert fast.score > slow.score
