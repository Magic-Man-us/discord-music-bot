"""AudioResolver implementation using yt-dlp for URL resolution and search."""

from __future__ import annotations

import asyncio
import hashlib
import re
import threading
import time
from typing import Any, Final, cast

from yt_dlp import YoutubeDL

from ...application.interfaces.audio_resolver import AudioResolver
from ...config.settings import AudioSettings
from ...domain.music.entities import PlaylistEntry, Track
from ...domain.music.wrappers import TrackId
from ...domain.shared.types import (
    HttpUrlStr,
    NonEmptyStr,
    PositiveInt,
)
from ...utils.logging import get_logger
from .models import (
    CACHE_MAX_SIZE,
    CACHE_TTL,
    DEFAULT_SEARCH_LIMIT,
    EXTRACT_TIMEOUT,
    HASH_ID_LENGTH,
    LOG_URL_TRUNCATE,
    RESOLVE_BATCH_DELAY,
    RESOLVE_BATCH_SIZE,
    AudioFormatInfo,
    CacheEntry,
    ExtractorArgs,
    YouTubeExtractorConfig,
    YtDlpExtractResult,
    YtDlpOpts,
    YtDlpTrackInfo,
)

logger = get_logger(__name__)


# ── Module-level state and patterns ────────────────────────────────────

_info_cache: dict[HttpUrlStr, CacheEntry] = {}
_cache_lock = threading.Lock()

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


def _generate_track_id(url: HttpUrlStr) -> str:
    match = YOUTUBE_ID_PATTERN.search(url)
    if match:
        return match.group(1)

    return hashlib.sha256(url.encode()).hexdigest()[:HASH_ID_LENGTH]


class YtDlpResolver(AudioResolver):
    def __init__(self, settings: AudioSettings | None = None) -> None:
        self._settings = settings or AudioSettings()
        self._format = (
            self._settings.ytdlp_format or "251/140/bestaudio[protocol^=http]/bestaudio/best"
        )

        self._extractor_args = ExtractorArgs(
            youtube=YouTubeExtractorConfig(
                pot_server_url=self._settings.pot_server_url,
                player_client=self._settings.player_client,
            )
        )

        self._base_opts = YtDlpOpts(
            format=self._format,
            extractor_args=self._extractor_args,
        )

        logger.info(
            "bgutil-ytdlp-pot-provider configured (server=%s)",
            self._settings.pot_server_url,
        )

    def _get_opts(self, **overrides: Any) -> YtDlpOpts:
        if overrides:
            return self._base_opts.model_copy(update=overrides)
        return self._base_opts

    def _get_playlist_opts(self) -> YtDlpOpts:
        return self._get_opts(noplaylist=False, extract_flat="in_playlist")

    def _info_to_track(self, info: YtDlpTrackInfo) -> Track | None:
        try:
            url = self._extract_webpage_url(info)
            if not url:
                logger.warning("No URL found in info dict")
                return None

            title = info.title
            stream_url = self._extract_stream_url(info)

            if not stream_url:
                logger.warning("No stream URL found for %s", title)
                return None

            track_id = _generate_track_id(url)

            artist = info.artist or info.creator
            uploader = info.uploader or info.channel

            return Track(
                id=TrackId(value=track_id),
                title=title,
                webpage_url=url,
                stream_url=stream_url,
                duration_seconds=info.duration,
                thumbnail_url=info.thumbnail,
                artist=artist,
                uploader=uploader,
                like_count=info.like_count,
                view_count=info.view_count,
            )
        except Exception:
            logger.exception("Failed to convert info to track")
            return None

    def _extract_webpage_url(self, info: YtDlpTrackInfo) -> str | None:
        return info.webpage_url or info.url

    def _extract_stream_url(self, info: YtDlpTrackInfo) -> str | None:
        if info.url:
            return info.url
        return self._extract_stream_from_formats(info.formats)

    @staticmethod
    def _extract_stream_from_formats(formats: list[AudioFormatInfo]) -> str | None:
        if not formats:
            return None
        audio_formats = [f for f in formats if f.acodec != "none" and f.url]
        if audio_formats:
            return audio_formats[-1].url
        return None

    @staticmethod
    def _parse_single_result(data: Any) -> YtDlpTrackInfo | None:
        """Parse a raw yt-dlp single-entry result into a typed model.

        Returns None if *data* is not a dict or fails validation.
        Extra fields are dropped by the model's ``extra="ignore"`` config.
        """
        if not isinstance(data, dict):
            return None
        try:
            return YtDlpTrackInfo.model_validate(data)
        except Exception:
            return None

    def _extract_info_sync(self, url: HttpUrlStr) -> YtDlpTrackInfo | None:
        now = time.time()
        with _cache_lock:
            cached = _info_cache.get(url)
            if cached is not None:
                if now - cached.cached_at < CACHE_TTL:
                    logger.debug("Cache hit for URL: %s", url[:LOG_URL_TRUNCATE])
                    return cached.info
                _info_cache.pop(url, None)

        try:
            with YoutubeDL(params=cast(Any, self._get_opts().model_dump())) as ydl:
                data = ydl.extract_info(url, download=False)
                result = self._parse_single_result(data)

                if result is not None:
                    with _cache_lock:
                        _info_cache[url] = CacheEntry(info=result, cached_at=now)
                        self._evict_cache(now)

                return result
        except Exception:
            logger.exception("Failed to extract info from %s", url)
            return None

    @staticmethod
    def _evict_cache(now: float) -> None:
        """Remove expired or oldest entries when the cache exceeds its size limit.

        Must be called while holding ``_cache_lock``.
        """
        if len(_info_cache) <= CACHE_MAX_SIZE:
            return

        expired = [k for k, entry in _info_cache.items() if now - entry.cached_at >= CACHE_TTL]
        if expired:
            for k in expired:
                _info_cache.pop(k, None)
            logger.debug("Cleaned %d expired cache entries", len(expired))
        else:
            # All entries are fresh — evict oldest
            oldest_key = min(_info_cache, key=lambda k: _info_cache[k].cached_at)
            _info_cache.pop(oldest_key, None)

    @staticmethod
    def _parse_extract_result(data: Any) -> YtDlpExtractResult:
        """Parse a raw yt-dlp multi-entry result into a typed model."""
        if not isinstance(data, dict):
            return YtDlpExtractResult()
        return YtDlpExtractResult.model_validate(data)

    def _search_sync(self, query: NonEmptyStr, limit: PositiveInt = 1) -> list[YtDlpTrackInfo]:
        try:
            search_query = f"ytsearch{limit}:{query}"
            with YoutubeDL(params=cast(Any, self._get_opts().model_dump())) as ydl:
                data = ydl.extract_info(search_query, download=False)
                return self._parse_extract_result(data).entries
        except Exception:
            logger.exception("Failed to search for %r", query)
            return []

    def _extract_playlist_sync(self, url: HttpUrlStr) -> list[YtDlpTrackInfo]:
        try:
            with YoutubeDL(params=cast(Any, self._get_playlist_opts().model_dump())) as ydl:
                data = ydl.extract_info(url, download=False)
                return self._parse_extract_result(data).entries
        except Exception:
            logger.exception("Failed to extract playlist from %s", url)
            return []

    async def resolve(self, query: NonEmptyStr) -> Track | None:
        try:
            async with asyncio.timeout(EXTRACT_TIMEOUT):
                if self.is_url(query):
                    info = await asyncio.to_thread(self._extract_info_sync, query)
                else:
                    results = await asyncio.to_thread(self._search_sync, query, 1)
                    info = results[0] if results else None

            if not info:
                return None

            return self._info_to_track(info)
        except TimeoutError:
            logger.error("yt-dlp extraction timed out after %ds for %r", EXTRACT_TIMEOUT, query)
            return None
        except Exception:
            logger.exception("Failed to resolve %r", query)
            return None

    async def resolve_many(self, queries: list[NonEmptyStr]) -> list[Track]:
        tracks: list[Track] = []

        # Process in batches to avoid overwhelming yt-dlp
        for i in range(0, len(queries), RESOLVE_BATCH_SIZE):
            batch = queries[i : i + RESOLVE_BATCH_SIZE]

            try:
                async with asyncio.TaskGroup() as tg:
                    batch_tasks = [tg.create_task(self.resolve(q)) for q in batch]

                for task in batch_tasks:
                    try:
                        result = task.result()
                        if result is not None:
                            tracks.append(result)
                    except Exception as e:
                        logger.warning("Resolution failed: %s", e)
            except* Exception as eg:
                for exc in eg.exceptions:
                    logger.warning("Resolution failed: %s", exc)

            if i + RESOLVE_BATCH_SIZE < len(queries):
                await asyncio.sleep(RESOLVE_BATCH_DELAY)

        return tracks

    async def search(
        self, query: NonEmptyStr, limit: PositiveInt = DEFAULT_SEARCH_LIMIT
    ) -> list[Track]:
        try:
            async with asyncio.timeout(EXTRACT_TIMEOUT):
                results = await asyncio.to_thread(self._search_sync, query, limit)

            tracks: list[Track] = []
            for info in results:
                track = self._info_to_track(info)
                if track:
                    tracks.append(track)

            return tracks
        except TimeoutError:
            logger.error("yt-dlp search timed out after %ds for %r", EXTRACT_TIMEOUT, query)
            return []
        except Exception as e:
            logger.error("Search failed for %r: %s", query, e)
            return []

    async def extract_playlist(self, url: HttpUrlStr) -> list[Track]:
        try:
            async with asyncio.timeout(EXTRACT_TIMEOUT):
                entries = await asyncio.to_thread(self._extract_playlist_sync, url)

            # Flat extraction returns metadata only, so resolve each entry individually
            tracks: list[Track] = []
            for entry in entries:
                entry_url = entry.url or entry.webpage_url
                if not entry_url:
                    continue
                track = await self.resolve(entry_url)
                if track:
                    tracks.append(track)

            return tracks
        except TimeoutError:
            logger.error(
                "yt-dlp playlist extraction timed out after %ds for %s", EXTRACT_TIMEOUT, url
            )
            return []
        except Exception as e:
            logger.error("Playlist extraction failed for %s: %s", url, e)
            return []

    async def preview_playlist(self, url: HttpUrlStr) -> list[PlaylistEntry]:
        try:
            async with asyncio.timeout(EXTRACT_TIMEOUT):
                entries = await asyncio.to_thread(self._extract_playlist_sync, url)

            results: list[PlaylistEntry] = []
            for entry in entries:
                entry_url = entry.url or entry.webpage_url
                if not entry_url:
                    continue
                results.append(
                    PlaylistEntry(
                        title=entry.title,
                        url=entry_url,
                        duration_seconds=entry.duration,
                    )
                )
            return results
        except TimeoutError:
            logger.error("yt-dlp playlist preview timed out after %ds for %s", EXTRACT_TIMEOUT, url)
            return []
        except Exception as e:
            logger.error("Playlist preview failed for %s: %s", url, e)
            return []

    def is_url(self, query: NonEmptyStr) -> bool:
        return any(pattern.search(query) for pattern in URL_PATTERNS)

    def is_playlist(self, url: HttpUrlStr) -> bool:
        return any(pattern.search(url) for pattern in PLAYLIST_PATTERNS)
