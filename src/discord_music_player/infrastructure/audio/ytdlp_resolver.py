"""AudioResolver implementation using yt-dlp for URL resolution and search."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from typing import Any, Final, cast

from yt_dlp import YoutubeDL

from discord_music_player.application.interfaces.audio_resolver import AudioResolver
from discord_music_player.config.settings import AudioSettings
from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.shared.messages import LogTemplates

logger = logging.getLogger(__name__)

CACHE_TTL: Final[int] = 3600
_info_cache: dict[str, tuple[dict[str, Any] | None, float]] = {}

URL_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"https?://"),
    re.compile(r"www\."),
]

PLAYLIST_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"[?&]list="),
    re.compile(r"/playlist\?"),
    re.compile(r"/sets/"),
]

YOUTUBE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})"
)


def _generate_track_id(url: str, title: str) -> str:
    match = YOUTUBE_ID_PATTERN.search(url)
    if match:
        return match.group(1)

    return hashlib.sha256(url.encode()).hexdigest()[:16]


class YtDlpResolver(AudioResolver):
    BASE_OPTS: Final[dict[str, Any]] = {
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,
        "default_search": "ytsearch",
        "forceipv4": True,
        "retries": 3,
        "socket_timeout": 10,
        "http_chunk_size": 1024 * 1024,
    }

    def __init__(self, settings: AudioSettings | None = None) -> None:
        self._settings = settings or AudioSettings()
        self._format = (
            self._settings.ytdlp_format or "251/140/bestaudio[protocol^=http]/bestaudio/best"
        )

        # bgutil-ytdlp-pot-provider fetches PO tokens; player_client avoids needing a JS runtime
        self._pot_opts: dict[str, Any] = {
            "extractor_args": {
                "youtube": {
                    "pot_server_url": self._settings.pot_server_url,
                    "player_client": ["android", "web"],
                }
            }
        }

        logger.info(
            LogTemplates.YTDLP_POT_CONFIGURED,
            self._settings.pot_server_url,
        )

    def _get_opts(self, **overrides: Any) -> dict[str, Any]:
        opts = dict(self.BASE_OPTS)
        opts["format"] = self._format
        opts["skip_download"] = True
        opts.update(self._pot_opts)
        opts.update(overrides)
        return opts

    def _get_playlist_opts(self) -> dict[str, Any]:
        opts = self._get_opts()
        opts["noplaylist"] = False
        opts["extract_flat"] = "in_playlist"
        return opts

    def _info_to_track(self, info: dict[str, Any]) -> Track | None:
        try:
            url = self._extract_webpage_url(info)
            if not url:
                logger.warning(LogTemplates.YTDLP_NO_URL_IN_INFO_DICT)
                return None

            title = info.get("title", "Unknown Title")
            stream_url = self._extract_stream_url(info)

            if not stream_url:
                logger.warning(LogTemplates.YTDLP_NO_STREAM_URL, title)
                return None

            track_id = _generate_track_id(url, title)

            artist = info.get("artist") or info.get("creator")
            uploader = info.get("uploader") or info.get("channel")

            like_count = info.get("like_count")
            if like_count is not None:
                try:
                    like_count = int(like_count)
                except (TypeError, ValueError):
                    like_count = None

            view_count = info.get("view_count")
            if view_count is not None:
                try:
                    view_count = int(view_count)
                except (TypeError, ValueError):
                    view_count = None

            return Track(
                id=TrackId(value=track_id),
                title=title,
                webpage_url=url,
                stream_url=stream_url,
                duration_seconds=info.get("duration"),
                thumbnail_url=info.get("thumbnail"),
                artist=artist,
                uploader=uploader,
                like_count=like_count,
                view_count=view_count,
            )
        except Exception:
            logger.exception(LogTemplates.YTDLP_FAILED_INFO_TO_TRACK)
            return None

    def _extract_webpage_url(self, info: dict[str, Any]) -> str | None:
        return info.get("webpage_url") or info.get("url")

    def _extract_stream_url(self, info: dict[str, Any]) -> str | None:
        stream_url = info.get("url")
        if stream_url:
            return stream_url
        return self._extract_stream_from_formats(info.get("formats", []))

    def _extract_stream_from_formats(self, formats: list[dict[str, Any]]) -> str | None:
        if not formats:
            return None
        audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("url")]
        if audio_formats:
            return audio_formats[-1].get("url")
        return None

    def _extract_info_sync(self, url: str) -> dict[str, Any] | None:
        now = time.time()
        if url in _info_cache:
            info, timestamp = _info_cache[url]
            if now - timestamp < CACHE_TTL:
                logger.debug(LogTemplates.CACHE_HIT_URL, url[:60])
                return info
            del _info_cache[url]

        try:
            with YoutubeDL(params=cast(Any, self._get_opts())) as ydl:
                data = ydl.extract_info(url, download=False)
                result = dict(data) if isinstance(data, dict) else None

                _info_cache[url] = (result, now)

                if len(_info_cache) > 500:
                    expired = [k for k, (_, ts) in _info_cache.items() if now - ts >= CACHE_TTL]
                    for k in expired:
                        del _info_cache[k]
                    if expired:
                        logger.debug(LogTemplates.CACHE_EXPIRED_CLEANED, len(expired))

                return result
        except Exception:
            logger.exception(LogTemplates.YTDLP_FAILED_EXTRACT_INFO, url)
            return None

    def _search_sync(self, query: str, limit: int = 1) -> list[dict[str, Any]]:
        try:
            search_query = f"ytsearch{limit}:{query}"
            with YoutubeDL(params=cast(Any, self._get_opts())) as ydl:
                data = ydl.extract_info(search_query, download=False)

                if not isinstance(data, dict):
                    return []

                entries = data.get("entries", [])
                if not isinstance(entries, list):
                    return []

                return [dict(e) for e in entries if e]
        except Exception:
            logger.exception(LogTemplates.YTDLP_FAILED_SEARCH, query)
            return []

    def _extract_playlist_sync(self, url: str) -> list[dict[str, Any]]:
        try:
            with YoutubeDL(params=cast(Any, self._get_playlist_opts())) as ydl:
                data = ydl.extract_info(url, download=False)

                if not isinstance(data, dict):
                    return []

                entries = data.get("entries", [])
                if not isinstance(entries, list):
                    return []

                return [dict(e) for e in entries if e]
        except Exception:
            logger.exception(LogTemplates.YTDLP_FAILED_EXTRACT_PLAYLIST, url)
            return []

    async def resolve(self, query: str) -> Track | None:
        try:
            if self.is_url(query):
                info = await asyncio.to_thread(self._extract_info_sync, query)
            else:
                results = await asyncio.to_thread(self._search_sync, query, 1)
                info = results[0] if results else None

            if not info:
                return None

            return self._info_to_track(info)
        except Exception:
            logger.exception(LogTemplates.YTDLP_FAILED_RESOLVE, query)
            return None

    async def resolve_many(self, queries: list[str]) -> list[Track]:
        """Resolve multiple queries to tracks.

        Args:
            queries: List of URLs or search queries.

        Returns:
            List of successfully resolved tracks.
        """
        tracks: list[Track] = []

        # Process in batches to avoid overwhelming yt-dlp
        batch_size = 5
        for i in range(0, len(queries), batch_size):
            batch = queries[i : i + batch_size]

            try:
                async with asyncio.TaskGroup() as tg:
                    batch_tasks = [tg.create_task(self.resolve(q)) for q in batch]

                # Collect results after TaskGroup completes
                for task in batch_tasks:
                    try:
                        result = task.result()
                        if result is not None:
                            tracks.append(result)
                    except Exception as e:
                        logger.warning(LogTemplates.RESOLUTION_FAILED.format(error=e))
            except* Exception as eg:
                # Handle exception group from TaskGroup
                for exc in eg.exceptions:
                    logger.warning(LogTemplates.RESOLUTION_FAILED.format(error=exc))

            # Small delay between batches
            if i + batch_size < len(queries):
                await asyncio.sleep(0.5)

        return tracks

    async def search(self, query: str, limit: int = 5) -> list[Track]:
        """Search for tracks matching a query.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of matching tracks.
        """
        try:
            results = await asyncio.to_thread(self._search_sync, query, limit)

            tracks: list[Track] = []
            for info in results:
                track = self._info_to_track(info)
                if track:
                    tracks.append(track)

            return tracks
        except Exception as e:
            logger.error(LogTemplates.SEARCH_FAILED.format(query=query, error=e))
            return []

    async def extract_playlist(self, url: str) -> list[Track]:
        """Extract all tracks from a playlist URL.

        Args:
            url: Playlist URL.

        Returns:
            List of tracks in the playlist.
        """
        try:
            entries = await asyncio.to_thread(self._extract_playlist_sync, url)

            # For flat extraction, we need to resolve each entry
            tracks: list[Track] = []
            for entry in entries:
                entry_url = entry.get("url") or entry.get("webpage_url")
                if entry_url:
                    track = await self.resolve(entry_url)
                    if track:
                        tracks.append(track)

            return tracks
        except Exception as e:
            logger.error(LogTemplates.PLAYLIST_FAILED.format(url=url, error=e))
            return []

    def is_url(self, query: str) -> bool:
        """Check if a query is a URL.

        Args:
            query: Query string to check.

        Returns:
            True if the query appears to be a URL.
        """
        return any(pattern.search(query) for pattern in URL_PATTERNS)

    def is_playlist(self, url: str) -> bool:
        """Check if a URL is a playlist.

        Args:
            url: URL to check.

        Returns:
            True if the URL appears to be a playlist.
        """
        return any(pattern.search(url) for pattern in PLAYLIST_PATTERNS)
