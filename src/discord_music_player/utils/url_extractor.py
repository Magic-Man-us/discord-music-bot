"""Utilities for detecting and normalizing external music platform URLs.

Detects Spotify and Apple Music URLs and converts them to YouTube search
queries so yt-dlp can resolve them.
"""

from __future__ import annotations

import re

_SPOTIFY_TRACK_PATTERN = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-z]+/)?track/([a-zA-Z0-9]+)"
)
_SPOTIFY_ALBUM_PATTERN = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-z]+/)?album/([a-zA-Z0-9]+)"
)
_APPLE_MUSIC_PATTERN = re.compile(
    r"https?://music\.apple\.com/.+/album/.+"
)


def is_spotify_url(query: str) -> bool:
    """Return True if the query is a Spotify track or album URL."""
    return _SPOTIFY_TRACK_PATTERN.search(query) is not None or _SPOTIFY_ALBUM_PATTERN.search(query) is not None


def is_apple_music_url(query: str) -> bool:
    """Return True if the query is an Apple Music URL."""
    return _APPLE_MUSIC_PATTERN.search(query) is not None


def is_external_music_url(query: str) -> bool:
    """Return True if the query is a Spotify or Apple Music URL."""
    return is_spotify_url(query) or is_apple_music_url(query)


_OG_TITLE_PATTERN = re.compile(
    r'<meta\s+(?:property|name)=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_HTML_TITLE_PATTERN = re.compile(
    r"<title[^>]*>([^<]+)</title>",
    re.IGNORECASE,
)
# Spotify titles usually look like: "Song Name - song and target by Artist Name | Spotify"
_SPOTIFY_TITLE_CLEANUP = re.compile(r"\s*\|\s*Spotify\s*$", re.IGNORECASE)
_SPOTIFY_TITLE_SEPARATOR = re.compile(r"\s*-\s*(?:song\s+(?:and\s+\w+\s+)?by|.*\s+by)\s+", re.IGNORECASE)


async def extract_search_query_from_url(url: str) -> str | None:
    """Fetch a Spotify/Apple Music URL and extract a search query from HTML metadata.

    Returns a string like "Artist - Song Name" suitable for YouTube search,
    or None if extraction fails.
    """
    import asyncio

    import urllib.request

    def _fetch() -> str | None:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; MusicBot/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                # Read only the head section (first 16KB) to avoid downloading the whole page
                html = resp.read(16384).decode("utf-8", errors="replace")
        except Exception:
            return None

        # Try OG title first
        match = _OG_TITLE_PATTERN.search(html)
        if match:
            return _clean_extracted_title(match.group(1))

        # Fallback to <title>
        match = _HTML_TITLE_PATTERN.search(html)
        if match:
            return _clean_extracted_title(match.group(1))

        return None

    try:
        return await asyncio.to_thread(_fetch)
    except Exception:
        return None


def _clean_extracted_title(raw_title: str) -> str:
    """Clean up a Spotify/Apple Music page title into a search query."""
    import html as html_module

    title = html_module.unescape(raw_title).strip()
    title = _SPOTIFY_TITLE_CLEANUP.sub("", title)

    # Spotify format: "Song Name - song and lyrics by Artist | Spotify"
    # After cleanup: "Song Name - song and lyrics by Artist"
    # We want: "Artist - Song Name" or just the cleaned title
    sep_match = _SPOTIFY_TITLE_SEPARATOR.search(title)
    if sep_match:
        song = title[: sep_match.start()].strip()
        artist = title[sep_match.end() :].strip()
        if artist and song:
            return f"{artist} - {song}"

    return title
