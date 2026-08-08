"""Tests for TLSRotator."""

from src.utils.tls_rotation import TLSRotator, IMPERSONATE_PROFILES


class TestTLSRotator:
    def test_next_profile_returns_valid(self):
        rotator = TLSRotator()
        profile = rotator.next_profile()
        assert profile in IMPERSONATE_PROFILES

    def test_rotation_cycles_all(self):
        rotator = TLSRotator()
        seen = set()
        for _ in range(len(IMPERSONATE_PROFILES)):
            seen.add(rotator.next_profile())
        assert seen == set(IMPERSONATE_PROFILES)

    def test_random_profile_valid(self):
        rotator = TLSRotator()
        profile = rotator.random_profile()
        assert profile in IMPERSONATE_PROFILES

    def test_custom_profiles(self):
        custom = ["chrome120", "firefox120"]
        rotator = TLSRotator(profiles=custom)
        assert rotator.next_profile() in custom

    def test_count(self):
        rotator = TLSRotator()
        assert rotator.count == len(IMPERSONATE_PROFILES)
