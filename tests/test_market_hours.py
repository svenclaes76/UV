"""Tests for uvalu/market_hours.py — the approximate 09:00–17:30 CET/CEST
weekday session clock used to pace the live price feed.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from uvalu.market_hours import is_market_hours

_CET = ZoneInfo("Europe/Brussels")


class TestIsMarketHours:
    def test_weekday_midday_is_open(self):
        # 2026-08-31 is a Monday
        assert is_market_hours(datetime(2026, 8, 31, 12, 0, tzinfo=_CET)) is True

    def test_weekday_before_open_is_closed(self):
        assert is_market_hours(datetime(2026, 8, 31, 8, 0, tzinfo=_CET)) is False

    def test_weekday_after_close_is_closed(self):
        assert is_market_hours(datetime(2026, 8, 31, 18, 0, tzinfo=_CET)) is False

    def test_open_boundary_is_inclusive(self):
        assert is_market_hours(datetime(2026, 8, 31, 9, 0, tzinfo=_CET)) is True

    def test_close_boundary_is_inclusive(self):
        assert is_market_hours(datetime(2026, 8, 31, 17, 30, tzinfo=_CET)) is True

    def test_saturday_is_closed(self):
        # 2026-08-29 is a Saturday
        assert is_market_hours(datetime(2026, 8, 29, 12, 0, tzinfo=_CET)) is False

    def test_sunday_is_closed(self):
        assert is_market_hours(datetime(2026, 8, 30, 12, 0, tzinfo=_CET)) is False

    def test_tz_aware_input_is_converted(self):
        # 10:00 UTC == 12:00 CEST (summer) → inside the window
        assert is_market_hours(datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)) is True
        # 16:00 UTC == 18:00 CEST → outside
        assert is_market_hours(datetime(2026, 8, 31, 16, 0, tzinfo=timezone.utc)) is False

    def test_naive_input_is_treated_as_cet(self):
        assert is_market_hours(datetime(2026, 8, 31, 12, 0)) is True
        assert is_market_hours(datetime(2026, 8, 31, 7, 0)) is False

    def test_no_argument_uses_current_time(self):
        # Smoke: must return a bool without raising, whatever "now" is.
        assert isinstance(is_market_hours(), bool)
