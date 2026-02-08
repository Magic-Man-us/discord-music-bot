"""Colored logging formatter for console output."""

from __future__ import annotations

import logging
import os
import sys


class ColoredFormatter(logging.Formatter):
    """Logging formatter that applies ANSI color codes to the levelname field.

    Colors are disabled when the ``NO_COLOR`` environment variable is set or
    when the output stream is not a TTY (e.g. redirected to a file).
    """

    COLORS: dict[int, str] = {
        logging.DEBUG: "\033[36m",     # cyan
        logging.INFO: "\033[32m",      # green
        logging.WARNING: "\033[33m",   # yellow
        logging.ERROR: "\033[31m",     # red
        logging.CRITICAL: "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def _use_color(self) -> bool:
        if os.environ.get("NO_COLOR") is not None:
            return False
        stream = getattr(self, "_stream", None) or sys.stdout
        return hasattr(stream, "isatty") and stream.isatty()

    def format(self, record: logging.LogRecord) -> str:
        if self._use_color():
            color = self.COLORS.get(record.levelno, "")
            record = logging.makeLogRecord(record.__dict__)
            record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)
