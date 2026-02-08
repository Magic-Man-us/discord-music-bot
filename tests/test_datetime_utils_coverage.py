"""
Additional DateTime Utilities Tests for Coverage

Tests edge cases and uncovered code paths in datetime_utils.
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from discord_music_player.domain.shared.datetime_utils import UtcDateTime, utcnow


class TestUtcDateTimeEdgeCases:
    """Tests for UtcDateTime edge cases and uncovered paths."""

    def test_init_with_naive_datetime_raises(self):
        """Should raise ValueError when datetime has no timezone."""
        naive_dt = datetime.now()  # No timezone

        with pytest.raises(ValueError, match="timezone-aware"):
            UtcDateTime(naive_dt)

    def test_init_with_non_utc_timezone_converts(self):
        """Should convert non-UTC timezone to UTC."""
        # Create a datetime in US Eastern timezone
        eastern = timezone(timedelta(hours=-5))
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=eastern)

        utc_dt = UtcDateTime(dt)

        # Should be converted to UTC (5 hours ahead)
        assert utc_dt.dt.hour == 17
        assert utc_dt.dt.tzinfo == UTC

    def test_from_iso_with_z_suffix(self):
        """Should parse ISO string with Z suffix."""
        iso_string = "2024-01-15T12:00:00Z"

        utc_dt = UtcDateTime.from_iso(iso_string)

        assert utc_dt.dt.year == 2024
        assert utc_dt.dt.month == 1
        assert utc_dt.dt.day == 15
        assert utc_dt.dt.hour == 12

    def test_from_iso_with_offset(self):
        """Should parse ISO string with explicit offset."""
        iso_string = "2024-01-15T12:00:00+00:00"

        utc_dt = UtcDateTime.from_iso(iso_string)

        assert utc_dt.dt.year == 2024
        assert utc_dt.dt.month == 1
        assert utc_dt.dt.day == 15

    def test_from_unix_seconds(self):
        """Should create from Unix timestamp."""
        # January 1, 2024 00:00:00 UTC
        timestamp = 1704067200

        utc_dt = UtcDateTime.from_unix_seconds(timestamp)

        assert utc_dt.dt.year == 2024
        assert utc_dt.dt.month == 1
        assert utc_dt.dt.day == 1

    def test_iso_property(self):
        """Should return ISO format with offset."""
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        utc_dt = UtcDateTime(dt)

        assert utc_dt.iso == "2024-01-15T12:00:00+00:00"

    def test_iso_z_property(self):
        """Should return ISO format with Z suffix."""
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        utc_dt = UtcDateTime(dt)

        assert utc_dt.iso_z == "2024-01-15T12:00:00Z"

    def test_unix_seconds_property(self):
        """Should return Unix timestamp in seconds."""
        # January 1, 2024 00:00:00 UTC
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        utc_dt = UtcDateTime(dt)

        assert utc_dt.unix_seconds == 1704067200

    def test_unix_millis_property(self):
        """Should return Unix timestamp in milliseconds."""
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        utc_dt = UtcDateTime(dt)

        assert utc_dt.unix_millis == 1704067200000

    def test_human_utc_property(self):
        """Should return human-readable UTC format."""
        dt = datetime(2024, 1, 15, 12, 30, 45, tzinfo=UTC)
        utc_dt = UtcDateTime(dt)

        assert utc_dt.human_utc == "2024-01-15 12:30:45 UTC"

    def test_discord_timestamp_default_style(self):
        """Should return Discord timestamp with default relative style."""
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        utc_dt = UtcDateTime(dt)

        timestamp = utc_dt.discord_timestamp()

        assert timestamp.startswith("<t:1704067200:")
        assert timestamp.endswith(":R>")

    def test_discord_timestamp_custom_style(self):
        """Should return Discord timestamp with custom style."""
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        utc_dt = UtcDateTime(dt)

        timestamp = utc_dt.discord_timestamp(style="f")

        assert timestamp == "<t:1704067200:f>"

    def test_now_returns_aware_datetime(self):
        """UtcDateTime.now() should return timezone-aware UTC datetime."""
        utc_dt = UtcDateTime.now()

        assert utc_dt.dt.tzinfo == UTC

    def test_utcnow_function(self):
        """utcnow() function should return timezone-aware UTC datetime."""
        dt = utcnow()

        assert dt.tzinfo == UTC
        assert isinstance(dt, datetime)

    def test_from_unix_seconds_with_float(self):
        """Should handle float timestamp by converting to int."""
        timestamp_float = 1704067200.5

        utc_dt = UtcDateTime.from_unix_seconds(timestamp_float)

        # Should truncate to 1704067200
        assert utc_dt.unix_seconds == 1704067200
