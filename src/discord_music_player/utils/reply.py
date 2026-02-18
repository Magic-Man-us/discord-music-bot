"""Utility functions for formatting Discord messages."""

from __future__ import annotations

from functools import cache
from urllib.parse import parse_qs, urlparse


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


def parse_timestamp(value: str) -> int | None:
    """Parse a timestamp string into total seconds.

    Accepts formats like "90", "1:30", or "1:30:00".
    Returns None if the input is invalid.
    """
    value = value.strip()
    if not value:
        return None

    parts = value.split(":")
    if len(parts) > 3:
        return None

    try:
        int_parts = [int(p) for p in parts]
    except ValueError:
        return None

    if any(p < 0 for p in int_parts):
        return None

    if len(int_parts) == 1:
        return int_parts[0]
    if len(int_parts) == 2:
        return int_parts[0] * 60 + int_parts[1]
    return int_parts[0] * 3600 + int_parts[1] * 60 + int_parts[2]


def extract_youtube_timestamp(url: str) -> int | None:
    """Extract the ``t=`` parameter (seconds) from a YouTube URL.

    Handles ``youtu.be/…?t=123``, ``youtube.com/watch?v=…&t=123``, and
    the ``t=1h2m3s`` / ``t=2m30s`` / ``t=90s`` human-readable variants.
    Returns None when no valid timestamp is present.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    host = (parsed.hostname or "").lower()
    if not any(h in host for h in ("youtube.com", "youtu.be", "youtube-nocookie.com")):
        return None

    params = parse_qs(parsed.query)
    raw = params.get("t", [None])[0]
    if raw is None:
        return None

    # Pure numeric (e.g. t=4778)
    try:
        return int(raw)
    except ValueError:
        pass

    # Human-readable (e.g. t=1h19m38s)
    import re

    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", raw)
    if match and any(match.groups()):
        h = int(match.group(1) or 0)
        m = int(match.group(2) or 0)
        s = int(match.group(3) or 0)
        return h * 3600 + m * 60 + s

    return None


@cache
def truncate(text: str, max_length: int = 90) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"
