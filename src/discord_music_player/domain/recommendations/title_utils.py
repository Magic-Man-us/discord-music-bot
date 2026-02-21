"""Pure-function utilities for parsing and cleaning track titles."""

from __future__ import annotations

import re
from typing import Final

# ── Precompiled patterns ────────────────────────────────────────────────

_TITLE_CLEANUP_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(
        r"\s*[\[\(](official\s*(video|audio|music\s*video|lyric\s*video|visualizer))\s*[\]\)]",
        re.IGNORECASE,
    ),
    re.compile(r"\s*[\[\(](lyrics?|with\s*lyrics?|letra)\s*[\]\)]", re.IGNORECASE),
    re.compile(r"\s*[\[\(](hd|hq|4k|1080p|720p)\s*[\]\)]", re.IGNORECASE),
    re.compile(r"\s*[\[\(](audio)\s*[\]\)]", re.IGNORECASE),
    re.compile(r"\s*[\[\(](remaster(ed)?|remix)\s*[\]\)]", re.IGNORECASE),
    re.compile(r"\s*[\[\(](ft\.?|feat\.?|featuring)\s+[^\]\)]+[\]\)]", re.IGNORECASE),
]

_ARTIST_BY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\s+by\s+(.+?)(?:\s*[\[\(]|$)", re.IGNORECASE,
)

_COMMON_NON_ARTIST_PREFIXES: Final[frozenset[str]] = frozenset({
    "official",
    "vevo",
    "music",
    "audio",
    "video",
    "topic",
    "lyrics",
    "lyric",
    "hd",
    "hq",
})

_ARTIST_DASH_SEPARATOR: Final[str] = " - "


def extract_artist_from_title(title: str) -> str | None:
    """Try to extract artist name from a track title.

    Common formats:
    - "Artist - Song Title"
    - "Song Title by Artist"
    """
    if _ARTIST_DASH_SEPARATOR in title:
        artist, _, _ = title.partition(_ARTIST_DASH_SEPARATOR)
        artist = artist.strip()
        if artist and artist.lower() not in _COMMON_NON_ARTIST_PREFIXES:
            return artist

    by_match = _ARTIST_BY_PATTERN.search(title)
    if by_match:
        return by_match.group(1).strip()

    return None


def clean_title(title: str) -> str:
    """Remove common suffixes like "(Official Video)", "[Lyrics]", etc."""
    result = title
    for pattern in _TITLE_CLEANUP_PATTERNS:
        result = pattern.sub("", result)
    return result.strip()
