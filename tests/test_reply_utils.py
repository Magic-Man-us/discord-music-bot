"""Tests for reply utility functions: parse_timestamp, extract_youtube_timestamp,
format_duration, and truncate."""

from __future__ import annotations

import pytest

from discord_music_player.utils.reply import (
    extract_youtube_timestamp,
    format_duration,
    parse_timestamp,
    truncate,
)


# =============================================================================
# parse_timestamp
# =============================================================================


class TestParseTimestamp:
    def test_plain_seconds(self):
        assert parse_timestamp("90") == 90

    def test_minutes_seconds(self):
        assert parse_timestamp("1:30") == 90

    def test_hours_minutes_seconds(self):
        assert parse_timestamp("1:30:00") == 5400

    def test_empty_string(self):
        assert parse_timestamp("") is None

    def test_whitespace_only(self):
        assert parse_timestamp("   ") is None

    def test_too_many_colons(self):
        assert parse_timestamp("1:2:3:4") is None

    def test_non_numeric(self):
        assert parse_timestamp("abc") is None

    def test_negative_value(self):
        assert parse_timestamp("-5") is None

    def test_negative_part(self):
        assert parse_timestamp("1:-30") is None

    def test_zero(self):
        assert parse_timestamp("0") == 0

    def test_whitespace_stripped(self):
        assert parse_timestamp("  90  ") == 90


# =============================================================================
# extract_youtube_timestamp
# =============================================================================


class TestExtractYoutubeTimestamp:
    def test_youtube_com_numeric(self):
        assert extract_youtube_timestamp("https://www.youtube.com/watch?v=abc&t=90") == 90

    def test_youtu_be_numeric(self):
        assert extract_youtube_timestamp("https://youtu.be/abc?t=90") == 90

    def test_m_youtube_com(self):
        assert extract_youtube_timestamp("https://m.youtube.com/watch?v=abc&t=90") == 90

    def test_human_readable_hms(self):
        # 1h19m38s = 3600 + 19*60 + 38 = 4778
        assert extract_youtube_timestamp("https://youtube.com/watch?v=abc&t=1h19m38s") == 4778

    def test_human_readable_ms(self):
        assert extract_youtube_timestamp("https://youtube.com/watch?v=abc&t=2m30s") == 150

    def test_human_readable_s_only(self):
        assert extract_youtube_timestamp("https://youtube.com/watch?v=abc&t=90s") == 90

    def test_missing_t_param(self):
        assert extract_youtube_timestamp("https://youtube.com/watch?v=abc") is None

    def test_non_youtube_url(self):
        assert extract_youtube_timestamp("https://example.com/watch?t=90") is None

    def test_t_zero(self):
        assert extract_youtube_timestamp("https://youtube.com/watch?v=abc&t=0") is None

    def test_exceeds_max_seek(self):
        assert extract_youtube_timestamp("https://youtube.com/watch?v=abc&t=999999") is None

    def test_invalid_url(self):
        assert extract_youtube_timestamp("not a url at all") is None


# =============================================================================
# format_duration
# =============================================================================


class TestFormatDuration:
    def test_none_returns_dash(self):
        assert format_duration(None) == "–"

    def test_seconds_only(self):
        assert format_duration(45) == "0:45"

    def test_minutes_and_seconds(self):
        assert format_duration(150) == "2:30"

    def test_hours_minutes_seconds(self):
        assert format_duration(3661) == "1:01:01"

    def test_zero(self):
        assert format_duration(0) == "0:00"

    def test_float_truncated(self):
        assert format_duration(90.9) == "1:30"


# =============================================================================
# truncate
# =============================================================================


class TestTruncate:
    def test_short_string_no_truncation(self):
        assert truncate("hello") == "hello"

    def test_exact_length(self):
        text = "x" * 90
        assert truncate(text) == text

    def test_over_length_adds_ellipsis(self):
        text = "x" * 100
        result = truncate(text)
        assert len(result) == 90
        assert result.endswith("…")

    def test_custom_max_length(self):
        result = truncate("hello world", max_length=5)
        assert result == "hell…"
        assert len(result) == 5
