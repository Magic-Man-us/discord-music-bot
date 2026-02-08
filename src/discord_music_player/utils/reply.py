"""Utility functions for formatting Discord messages."""

from __future__ import annotations

from functools import cache


@cache
def format_duration(seconds: int | float | None) -> str:
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
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"
