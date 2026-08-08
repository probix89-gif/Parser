"""Tests for BatchManager."""

import asyncio
import tempfile
import os

from src.bot.batch_manager import BatchManager, BatchProgress, ThroughputMetrics
from src.core.filters import URLFilter
from src.core.proxy_pool import ProxyPool
from src.models.config import BotConfig
from src.utils.tls_rotation import TLSRotator
from src.utils.ua_rotation import UserAgentRotator


DORK_FILE_CONTENT = """site:example.com "gift card"
inurl:login site:*.com
# this is a comment

intitle:"index of" "parent directory"
"""


class TestBatchManagerParsing:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.blocklist_path = os.path.join(self.tmpdir, "blocklist.txt")
        with open(self.blocklist_path, "w") as f:
            f.write("google.com\nyahoo.com\ngithub.com\n")

        self.config = BotConfig(token="test")
        self.proxy_pool = ProxyPool("/nonexistent", max_failures=3)
        self.tls = TLSRotator()
        self.ua = UserAgentRotator("/nonexistent")
        self.url_filter = URLFilter(self.blocklist_path)
        self.batch_mgr = BatchManager(
            self.config, self.proxy_pool, self.tls, self.ua, self.url_filter
        )

    def test_parse_dork_file_basic(self):
        dorks = self.batch_mgr.parse_dork_file(DORK_FILE_CONTENT)
        assert len(dorks) == 3  # 2 dorks + 1 more = 3 non-comment, non-blank
        assert "# this is a comment" not in dorks

    def test_parse_dork_file_skips_blanks(self):
        content = "dork1\n\n\ndork2\n"
        dorks = self.batch_mgr.parse_dork_file(content)
        assert len(dorks) == 2
        assert "" not in dorks

    def test_parse_dork_file_skips_comments(self):
        content = "# comment\ndork1\n# another\ndork2\n"
        dorks = self.batch_mgr.parse_dork_file(content)
        assert len(dorks) == 2
        assert all(not d.startswith("#") for d in dorks)

    def test_parse_dork_file_truncates_at_max(self):
        content = "\n".join([f"site:test{i}.com" for i in range(600)])
        dorks = self.batch_mgr.parse_dork_file(content)
        assert len(dorks) == BatchManager.MAX_DORKS

    def test_parse_dork_file_empty(self):
        dorks = self.batch_mgr.parse_dork_file("")
        assert dorks == []


class TestBatchProgress:
    def test_pct_zero_when_total_zero(self):
        p = BatchProgress(total=0)
        assert p.pct == 0.0

    def test_pct_calculated(self):
        p = BatchProgress(total=100, completed=50)
        assert p.pct == 50.0

    def test_urls_per_sec(self):
        from datetime import datetime, timedelta
        p = BatchProgress(total=100, completed=50, total_urls=500)
        p.started_at = datetime.now() - timedelta(seconds=10)
        assert 40 <= p.urls_per_sec <= 60


class TestThroughputMetrics:
    def test_req_per_sec(self):
        import time
        m = ThroughputMetrics(requests_sent=100)
        m.start_time = time.monotonic() - 10
        assert 9 <= m.req_per_sec <= 11

    def test_success_rate(self):
        m = ThroughputMetrics(requests_sent=100, requests_succeeded=80)
        assert m.success_rate == 0.8

    def test_success_rate_zero(self):
        m = ThroughputMetrics()
        assert m.success_rate == 0.0


class TestExportToFile:
    def test_export_creates_file(self):
        tmpdir = tempfile.mkdtemp()
        output_path = os.path.join(tmpdir, "sub", "results.txt")
        urls = ["https://example.com/page1", "https://example.com/page2"]

        result_path = BatchManager.export_to_file(urls, output_path)

        assert os.path.exists(result_path)
        with open(result_path) as f:
            content = f.read()
        assert "https://example.com/page1" in content
        assert "https://example.com/page2" in content
        assert content.count("\n") == 2

    def test_export_full_urls(self):
        tmpdir = tempfile.mkdtemp()
        output_path = os.path.join(tmpdir, "results.txt")
        urls = [f"https://site{i}.com/page" for i in range(100)]

        BatchManager.export_to_file(urls, output_path)

        with open(output_path) as f:
            lines = f.read().strip().splitlines()
        assert len(lines) == 100
