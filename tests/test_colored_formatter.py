"""Tests for ColoredFormatter."""

import logging
from io import StringIO
from unittest.mock import patch

import pytest

from discord_music_player.utils.logging import ColoredFormatter

RESET = "\033[0m"
LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[1;31m",
}


def _make_record(level: int, message: str = "test") -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger",
        level=level,
        pathname="test.py",
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


class TestColoredFormatter:
    """Tests for ANSI color formatting."""

    def _tty_formatter(self) -> ColoredFormatter:
        fmt = ColoredFormatter("%(levelname)s | %(message)s")
        # Simulate a TTY stream
        stream = StringIO()
        stream.isatty = lambda: True  # type: ignore[attr-defined]
        fmt._stream = stream  # type: ignore[attr-defined]
        return fmt

    @pytest.mark.parametrize(
        "level",
        [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL],
    )
    def test_color_applied_per_level(self, level: int):
        """Should apply the correct ANSI color code for each level."""
        fmt = self._tty_formatter()
        record = _make_record(level)
        output = fmt.format(record)

        color = LEVEL_COLORS[level]
        assert color in output
        assert RESET in output

    def test_no_color_when_no_color_env_set(self):
        """Should not apply colors when NO_COLOR env var is set."""
        fmt = self._tty_formatter()
        record = _make_record(logging.INFO)

        with patch.dict("os.environ", {"NO_COLOR": "1"}):
            output = fmt.format(record)

        assert "\033[" not in output

    def test_no_color_when_stream_not_tty(self):
        """Should not apply colors when stream is not a TTY."""
        fmt = ColoredFormatter("%(levelname)s | %(message)s")
        # StringIO.isatty() returns False by default
        fmt._stream = StringIO()  # type: ignore[attr-defined]
        record = _make_record(logging.ERROR)
        output = fmt.format(record)

        assert "\033[" not in output

    def test_format_output_matches_pattern(self):
        """Should produce output matching the configured format string."""
        fmt = self._tty_formatter()
        record = _make_record(logging.INFO, "hello world")
        output = fmt.format(record)

        # Strip ANSI codes for content check
        plain = output.replace(LEVEL_COLORS[logging.INFO], "").replace(RESET, "")
        assert "INFO" in plain
        assert "hello world" in plain
        assert "|" in plain

    def test_original_record_not_mutated(self):
        """Should not mutate the original LogRecord."""
        fmt = self._tty_formatter()
        record = _make_record(logging.WARNING)
        original_levelname = record.levelname

        fmt.format(record)

        assert record.levelname == original_levelname
