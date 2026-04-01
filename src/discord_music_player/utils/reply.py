"""Utility functions for formatting Discord messages."""

from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from ..domain.shared.constants import (
    AudioConstants,
    UIConstants,
    YouTubeDomains,
)

if TYPE_CHECKING:
    from discord_music_player.domain.music.entities import Track

_MAX_TIMESTAMP_PARTS = 3


@lru_cache(maxsize=512)
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
    value = value.strip()
    if not value:
        return None

    parts = value.split(":")
    if len(parts) > _MAX_TIMESTAMP_PARTS:
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
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    host = (parsed.hostname or "").lower()
    if host not in YouTubeDomains.ALL:
        return None

    params = parse_qs(parsed.query)
    raw = params.get("t", [None])[0]
    if raw is None:
        return None

    max_seconds = AudioConstants.MAX_SEEK_SECONDS

    try:
        value = int(raw)
        return value if 0 < value <= max_seconds else None
    except ValueError:
        pass

    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", raw)
    if match and any(match.groups()):
        h = int(match.group(1) or 0)
        m = int(match.group(2) or 0)
        s = int(match.group(3) or 0)
        value = h * 3600 + m * 60 + s
        return value if 0 < value <= max_seconds else None

    return None


@lru_cache(maxsize=512)
def truncate(text: str, max_length: int = 90) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def deduplicate_tracks(tracks: list[Track]) -> list[Track]:
    """Remove duplicate tracks by ID, preserving first-seen order."""
    seen: set[str] = set()
    unique: list[Track] = []
    for track in tracks:
        if track.id.value not in seen:
            seen.add(track.id.value)
            unique.append(track)
    return unique


def paginate(
    total_items: int,
    page: int,
    per_page: int = UIConstants.QUEUE_PER_PAGE,
) -> tuple[int, int, int]:
    """Return (clamped_page, total_pages, start_index) for paginated display."""
    total_pages = max(1, math.ceil(total_items / per_page))
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * per_page
    return page, total_pages, start_idx
