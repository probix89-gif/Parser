"""Tests for UserAgentRotator."""

import tempfile
import os

from src.utils.ua_rotation import UserAgentRotator


UA_CONTENT = """Mozilla/5.0 Chrome/120
Mozilla/5.0 Chrome/119
Mozilla/5.0 Firefox/120
# This is a comment

Mozilla/5.0 Safari/17
"""


class TestUserAgentRotator:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ua_path = os.path.join(self.tmpdir, "ua.txt")
        with open(self.ua_path, "w") as f:
            f.write(UA_CONTENT)
        self.rotator = UserAgentRotator(self.ua_path)

    def test_next_returns_nonempty(self):
        ua = self.rotator.next()
        assert len(ua) > 0
        assert "Mozilla" in ua

    def test_rotation_cycles_all(self):
        seen = set()
        for _ in range(3):  # 3 non-comment UAs
            seen.add(self.rotator.next())
        assert len(seen) == 3

    def test_random_returns_valid(self):
        ua = self.rotator.random()
        assert "Mozilla" in ua

    def test_count(self):
        assert self.rotator.count == 4  # 4 non-comment, non-blank lines

    def test_fallback_when_file_missing(self):
        rotator = UserAgentRotator("/nonexistent/path")
        assert len(rotator.agents) == 1
        assert "Chrome" in rotator.next()

    def test_comments_skipped(self):
        for _ in range(5):
            ua = self.rotator.next()
            assert "# This is a comment" not in ua
