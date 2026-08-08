"""Tests for YahooSerpsParser."""

from src.core.parser import YahooSerpsParser


SAMPLE_HTML = """
<html><body>
<div id="results">
  <a href="https://r.search.yahoo.com/_ylt=Awrn/RU=https%3A%2F%2Fexample.com%2Fpage1/RK=2">Result 1</a>
  <a href="https://r.search.yahoo.com/_ylt=Bwrn/RU=https%3A%2F%2Fgift-card-site.com%2Fbalance/RK=3">Result 2</a>
  <a href="https://www.example.org/login">Direct link</a>
  <a href="https://search.yahoo.com/page">Yahoo internal</a>
  <a href="https://blocked-site.com/page">Another direct</a>
  <a href="https://r.search.yahoo.com/RU=https%3A%2F%2Fexample.com%2Fpage1/RK=2">Duplicate</a>
</div>
</body></html>
"""


class TestYahooSerpsParser:
    def test_parse_redirect_urls(self):
        urls = YahooSerpsParser.parse(SAMPLE_HTML)
        assert "https://example.com/page1" in urls
        assert "https://gift-card-site.com/balance" in urls

    def test_parse_direct_urls(self):
        urls = YahooSerpsParser.parse(SAMPLE_HTML)
        assert "https://www.example.org/login" in urls
        assert "https://blocked-site.com/page" in urls

    def test_yahoo_internal_excluded(self):
        urls = YahooSerpsParser.parse(SAMPLE_HTML)
        assert "https://search.yahoo.com/page" not in urls

    def test_deduplication(self):
        urls = YahooSerpsParser.parse(SAMPLE_HTML)
        # example.com/page1 appears twice (redirect), should be deduplicated
        count = urls.count("https://example.com/page1")
        assert count == 1

    def test_empty_html(self):
        urls = YahooSerpsParser.parse("<html></html>")
        assert urls == []

    def test_malformed_html(self):
        urls = YahooSerpsParser.parse("<html><body><a>no href</a></body></html>")
        assert urls == []
