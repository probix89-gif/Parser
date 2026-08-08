"""Integration test — end-to-end pipeline: build → parse → filter → format → export."""

import os
import tempfile

from src.bot.batch_manager import BatchManager
from src.bot.formatter import format_results
from src.core.filters import URLFilter
from src.core.parser import YahooSerpsParser
from src.core.query_builder import YahooQueryBuilder


SAMPLE_SERP_HTML = """
<html><body>
<div id="results">
  <a href="https://r.search.yahoo.com/_ylt=A/RU=https%3A%2F%2Fgiftcards-site.com%2Fcheck-balance/RK=1">Gift Card Balance</a>
  <a href="https://r.search.yahoo.com/_ylt=B/RU=https%3A%2F%2Fmy-store.com%2Fgift-cards/RK=2">My Store Gift Cards</a>
  <a href="https://r.search.yahoo.com/_ylt=C/RU=https%3A%2F%2Fexample.org%2Flogin/RK=3">Login Page</a>
  <a href="https://r.search.yahoo.com/_ylt=D/RU=https%3A%2F%2Fgoogle.com%2Fsearch/RK=4">Google Search</a>
  <a href="https://r.search.yahoo.com/_ylt=E/RU=https%3A%2F%2Fgithub.com%2Frepo/RK=5">GitHub Repo</a>
  <a href="https://r.search.yahoo.com/_ylt=F/RU=https%3A%2F%2Funknown-site.com%2Findex.html/RK=6">Unknown Site</a>
</div>
</body></html>
"""

BLOCKLIST = """google.com
yahoo.com
github.com
microsoft.com
amazon.com
"""


class TestIntegration:
    def test_full_pipeline(self):
        # 1. Build query URLs
        qb = YahooQueryBuilder()
        urls = qb.build("site:example.com gift card", pages=2)
        assert len(urls) == 2

        # 2. Parse sample HTML
        parsed = YahooSerpsParser.parse(SAMPLE_SERP_HTML)
        assert len(parsed) > 0

        # 3. Filter
        tmpdir = tempfile.mkdtemp()
        blocklist_path = os.path.join(tmpdir, "blocklist.txt")
        with open(blocklist_path, "w") as f:
            f.write(BLOCKLIST)
        url_filter = URLFilter(blocklist_path)
        clean = url_filter.filter(parsed)

        # Blocked domains should be removed
        assert all("google.com" not in u for u in clean)
        assert all("yahoo.com" not in u for u in clean)
        assert all("github.com" not in u for u in clean)

        # Good URLs should survive
        assert any("giftcards-site.com" in u for u in clean)
        assert any("my-store.com" in u for u in clean)
        assert any("unknown-site.com" in u for u in clean)

        # /login path should be filtered
        assert all("login" not in u for u in clean)

        # 4. Format
        messages = format_results(clean, "Integration Test")
        assert len(messages) > 0
        assert all(len(m) <= 4096 for m in messages)
        assert "Integration Test" in messages[0]

        # 5. Export to file
        output_path = os.path.join(tmpdir, "export", "results.txt")
        BatchManager.export_to_file(clean, output_path)
        assert os.path.exists(output_path)
        with open(output_path) as f:
            lines = f.read().strip().splitlines()
        assert len(lines) == len(clean)


class TestFormatter:
    def test_format_results_basic(self):
        urls = [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://other.com/index",
        ]
        messages = format_results(urls, "Test Dork")
        assert len(messages) >= 1
        assert "Test Dork" in messages[0]
        assert "example.com" in messages[0].lower()
        assert "3 URLs" in messages[0]

    def test_pagination(self):
        urls = [f"https://site{i}.com/page" for i in range(120)]
        messages = format_results(urls, "Mass", per_page=50)
        assert len(messages) >= 3  # 120 / 50 = 3 pages

    def test_message_under_4096(self):
        urls = [f"https://example.com/{i}" for i in range(500)]
        messages = format_results(urls, "Test")
        for msg in messages:
            assert len(msg) <= 4096

    def test_top_domains_shown(self):
        urls = [
            "https://a.com/1", "https://a.com/2", "https://a.com/3",
            "https://b.com/1", "https://b.com/2",
            "https://c.com/1",
        ]
        messages = format_results(urls, "Test")
        assert "a.com" in messages[0]


class TestDorkBotParseArgs:
    def test_parse_args_no_pages(self):
        from src.bot.handlers import DorkBot
        dork, pages = DorkBot.parse_args(["site:example.com", "gift", "card"])
        assert dork == "site:example.com gift card"
        assert pages == 10

    def test_parse_args_with_pages(self):
        from src.bot.handlers import DorkBot
        dork, pages = DorkBot.parse_args(["site:example.com", "--pages", "30"])
        assert dork == "site:example.com"
        assert pages == 30

    def test_parse_args_pages_clamped_60(self):
        from src.bot.handlers import DorkBot
        dork, pages = DorkBot.parse_args(["test", "--pages", "100"])
        assert pages == 60

    def test_parse_args_pages_clamped_1(self):
        from src.bot.handlers import DorkBot
        dork, pages = DorkBot.parse_args(["test", "--pages", "0"])
        assert pages == 1

    def test_parse_pages_from_caption(self):
        from src.bot.handlers import DorkBot
        assert DorkBot.parse_pages_from_caption("--pages 45") == 45
        assert DorkBot.parse_pages_from_caption("no pages here") == 10
        assert DorkBot.parse_pages_from_caption("--pages 100") == 60
        assert DorkBot.parse_pages_from_caption("") == 10
