"""Utility functions for formatting Discord messages."""

from __future__ import annotations

from functools import cache


@cache
def format_duration(seconds: int | float | None) -> str:
    """Format duration in seconds to human-readable MM:SS or HH:MM:SS.

    Args:
        seconds: Duration in seconds (can be None).

    Returns:
        Formatted string like "3:45" or "1:23:45", or "–" if None.
    """
    if seconds is None:
        return "–"

    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


@cache
def truncate(text: str, max_length: int = 90) -> str:
    """Truncate text with ellipsis if needed.

    Args:
        text: The text to truncate.
        max_length: Maximum length before truncation.

    Returns:
        Truncated string with "…" if over max_length.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"
