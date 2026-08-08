"""Tests for URLFilter."""

from src.core.filters import URLFilter


BLOCKLIST_CONTENT = """google.com
yahoo.com
github.com
microsoft.com
amazon.com
"""


class TestURLFilter:
    def setup_method(self, tmp_path_factory=None):
        import tempfile, os
        self.tmpdir = tempfile.mkdtemp()
        self.blocklist_path = os.path.join(self.tmpdir, "blocklist.txt")
        with open(self.blocklist_path, "w") as f:
            f.write(BLOCKLIST_CONTENT)
        self.url_filter = URLFilter(self.blocklist_path)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_blocklisted_domains_removed(self):
        urls = [
            "https://google.com/page",
            "https://yahoo.com/search",
            "https://github.com/repo",
            "https://example.com/page",
        ]
        filtered = self.url_filter.filter(urls)
        assert "https://example.com/page" in filtered
        assert "https://google.com/page" not in filtered
        assert "https://yahoo.com/search" not in filtered
        assert "https://github.com/repo" not in filtered

    def test_subdomains_of_blocked_removed(self):
        urls = [
            "https://mail.google.com/inbox",
            "https://docs.github.com/guide",
            "https://shop.amazon.com/product",
            "https://example.org/page",
        ]
        filtered = self.url_filter.filter(urls)
        assert "https://example.org/page" in filtered
        assert "https://mail.google.com/inbox" not in filtered
        assert "https://docs.github.com/guide" not in filtered
        assert "https://shop.amazon.com/product" not in filtered

    def test_blocked_paths_removed(self):
        urls = [
            "https://example.com/login",
            "https://example.com/auth/token",
            "https://example.com/search?q=test",
            "https://example.com/page",
        ]
        filtered = self.url_filter.filter(urls)
        assert "https://example.com/page" in filtered
        assert "https://example.com/login" not in filtered
        assert "https://example.com/auth/token" not in filtered
        assert "https://example.com/search?q=test" not in filtered

    def test_deduplication(self):
        urls = [
            "https://example.com/page",
            "https://example.com/page",
            "https://example.com/other",
        ]
        filtered = self.url_filter.filter(urls)
        assert filtered.count("https://example.com/page") == 1
        assert "https://example.com/other" in filtered

    def test_non_http_filtered(self):
        urls = [
            "ftp://example.com/file",
            "javascript:void(0)",
            "https://example.com/page",
        ]
        filtered = self.url_filter.filter(urls)
        assert "https://example.com/page" in filtered
        assert all(u.startswith("http") for u in filtered)

    def test_blocklist_count(self):
        assert self.url_filter.blocklist_count == 5
