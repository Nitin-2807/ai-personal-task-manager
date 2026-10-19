"""
Tests for the shared date/time helpers.

Covers time normalization, period normalization, 12-hour display,
due-date formatting, and configured-timezone handling.
"""

from datetime import date, datetime, timezone

import pytest

from src.date_utils import (
    TIME_PERIODS,
    format_due,
    format_time_12h,
    normalize_period_value,
    normalize_time_value,
    timezone_object,
    today_in_timezone,
)


class TestNormalizeTimeValue:
    """Exact times must normalize to 24-hour HH:MM storage."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("3 PM", "15:00"),
            ("3:30 PM", "15:30"),
            ("3:30PM", "15:30"),
            ("10 AM", "10:00"),
            ("12 AM", "00:00"),
            ("12 PM", "12:00"),
            ("12:05 am", "00:05"),
            ("15:00", "15:00"),
            ("00:00", "00:00"),
            ("23:59", "23:59"),
            ("7:05 p.m.", "19:05"),
            ("noon", "12:00"),
            ("midnight", "00:00"),
        ],
    )
    def test_common_formats_normalize(self, raw, expected):
        assert normalize_time_value(raw) == expected

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_is_none(self, empty):
        assert normalize_time_value(empty) is None

    @pytest.mark.parametrize(
        "raw",
        ["25:00", "12:75", "0 PM", "13 PM", "abc", "3", "3 PM tomorrow", "24:00"],
    )
    def test_invalid_or_ambiguous_rejected(self, raw):
        with pytest.raises(ValueError):
            normalize_time_value(raw)


class TestNormalizePeriodValue:
    """Approximate periods must never become exact times."""

    @pytest.mark.parametrize("period", TIME_PERIODS)
    def test_supported_periods_pass_through(self, period):
        assert normalize_period_value(period) == period

    def test_case_and_whitespace_are_normalized(self):
        assert normalize_period_value("  Evening. ") == "evening"

    def test_tonight_alias_maps_to_evening(self):
        assert normalize_period_value("tonight") == "evening"

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_is_none(self, empty):
        assert normalize_period_value(empty) is None

    def test_unknown_period_rejected(self):
        with pytest.raises(ValueError):
            normalize_period_value("dawn")


class TestFormatting:
    """Display helpers must render readable 12-hour times."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("15:00", "3:00 PM"),
            ("10:00", "10:00 AM"),
            ("00:05", "12:05 AM"),
            ("12:30", "12:30 PM"),
            ("23:59", "11:59 PM"),
        ],
    )
    def test_format_time_12h(self, raw, expected):
        assert format_time_12h(raw) == expected

    def test_format_due_without_time(self):
        assert format_due(date(2026, 10, 20)) == "2026-10-20"

    def test_format_due_with_exact_time(self):
        assert (
            format_due(date(2026, 10, 20), due_time="15:00")
            == "2026-10-20 at 3:00 PM"
        )

    def test_format_due_with_period(self):
        assert (
            format_due(date(2026, 10, 20), due_period="evening")
            == "2026-10-20 (evening)"
        )

    def test_format_due_prefers_exact_time(self):
        assert (
            format_due(date(2026, 10, 20), due_time="09:00", due_period="morning")
            == "2026-10-20 at 9:00 AM"
        )


class TestTimezoneHandling:
    """Dates must come from the explicitly configured timezone."""

    def test_today_in_utc_matches_utc_clock(self):
        expected = datetime.now(timezone.utc).date()
        assert today_in_timezone("UTC") == expected

    def test_today_in_configured_timezone_returns_date(self):
        result = today_in_timezone("Asia/Kolkata")
        assert isinstance(result, date)

    def test_unknown_timezone_raises_clear_error(self):
        with pytest.raises(ValueError, match="Unknown TIMEZONE"):
            timezone_object("Not/AZone")

    def test_invalid_timezone_fails_config_validation(self, monkeypatch):
        from src.config import Config

        monkeypatch.setattr(Config, "TIMEZONE", "Not/AZone")
        with pytest.raises(ValueError, match="Unknown TIMEZONE"):
            Config.validate()
