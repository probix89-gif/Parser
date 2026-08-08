"""Tests for YahooQueryBuilder."""

from src.core.query_builder import YahooQueryBuilder


class TestYahooQueryBuilder:
    def test_single_page(self):
        qb = YahooQueryBuilder()
        urls = qb.build("site:example.com", pages=1)
        assert len(urls) == 1
        assert "search.yahoo.com/search" in urls[0]
        assert "p=site%3Aexample.com" in urls[0]
        assert "b=1" in urls[0]

    def test_multi_page_offsets(self):
        qb = YahooQueryBuilder()
        urls = qb.build("test query", pages=5)
        assert len(urls) == 5
        for i, url in enumerate(urls):
            offset = i * 10 + 1
            assert f"b={offset}" in url

    def test_special_characters_encoded(self):
        qb = YahooQueryBuilder()
        urls = qb.build('intitle:"index of"', pages=1)
        assert "intitle%3A%22index+of%22" in urls[0] or "intitle%3A%22index%20of%22" in urls[0]

    def test_pages_clamped_to_60(self):
        qb = YahooQueryBuilder()
        urls = qb.build("test", pages=100)
        assert len(urls) == 60

    def test_pages_clamped_to_1(self):
        qb = YahooQueryBuilder()
        urls = qb.build("test", pages=0)
        assert len(urls) == 1

    def test_build_single(self):
        qb = YahooQueryBuilder()
        url = qb.build_single("test")
        assert "search.yahoo.com/search" in url
        assert "p=test" in url
