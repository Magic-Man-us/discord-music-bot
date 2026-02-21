"""AudioResolver implementation using yt-dlp for URL resolution and search."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from typing import Any, Final, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator
from yt_dlp import YoutubeDL

from discord_music_player.application.interfaces.audio_resolver import AudioResolver
from discord_music_player.config.settings import AudioSettings
from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.shared.messages import LogTemplates

logger = logging.getLogger(__name__)

CACHE_TTL: Final[int] = 3600


# ── Pydantic models for yt-dlp data ────────────────────────────────────


class AudioFormatInfo(BaseModel):
    """A single audio format entry from yt-dlp extraction."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    url: str | None = None
    acodec: str | None = None


class YtDlpTrackInfo(BaseModel):
    """Trimmed yt-dlp extraction result for caching and track conversion.

    Extra fields from yt-dlp are silently ignored, keeping memory usage low.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    webpage_url: str | None = None
    url: str | None = None
    title: str = "Unknown Title"
    duration: int | None = None
    thumbnail: str | None = None
    artist: str | None = None
    creator: str | None = None
    uploader: str | None = None
    channel: str | None = None
    like_count: int | None = None
    view_count: int | None = None
    formats: list[AudioFormatInfo] = Field(default_factory=list)

    @field_validator("like_count", "view_count", mode="before")
    @classmethod
    def _coerce_count(cls, v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None


class CacheEntry(BaseModel):
    """Cached yt-dlp extraction result with expiry timestamp."""

    model_config = ConfigDict(frozen=True)

    info: YtDlpTrackInfo | None = None
    cached_at: float


# ── yt-dlp option models ───────────────────────────────────────────────


class YouTubeExtractorConfig(BaseModel):
    """YouTube-specific yt-dlp extractor arguments."""

    model_config = ConfigDict(frozen=True)

    pot_server_url: str
    player_client: list[str] = Field(default_factory=lambda: ["android", "web"])


class ExtractorArgs(BaseModel):
    """Container for yt-dlp extractor arguments."""

    model_config = ConfigDict(frozen=True)

    youtube: YouTubeExtractorConfig


class YtDlpOpts(BaseModel):
    """Typed yt-dlp configuration options passed to YoutubeDL."""

    model_config = ConfigDict(frozen=True)

    quiet: bool = True
    noprogress: bool = True
    noplaylist: bool = True
    default_search: str = "ytsearch"
    forceipv4: bool = True
    retries: int = 3
    socket_timeout: int = 10
    http_chunk_size: int = 1024 * 1024
    format: str | None = None
    skip_download: bool = True
    extract_flat: str | bool = False
    extractor_args: ExtractorArgs | None = None


# ── Module-level state and patterns ────────────────────────────────────

_info_cache: dict[str, CacheEntry] = {}

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

    def __init__(self, settings: AudioSettings | None = None) -> None:
        self._settings = settings or AudioSettings()
        self._format = (
            self._settings.ytdlp_format or "251/140/bestaudio[protocol^=http]/bestaudio/best"
        )

        self._extractor_args = ExtractorArgs(
            youtube=YouTubeExtractorConfig(
                pot_server_url=self._settings.pot_server_url,
            )
        )

        self._base_opts = YtDlpOpts(
            format=self._format,
            extractor_args=self._extractor_args,
        )

        logger.info(
            LogTemplates.YTDLP_POT_CONFIGURED,
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
                logger.warning(LogTemplates.YTDLP_NO_URL_IN_INFO_DICT)
                return None

            title = info.title
            stream_url = self._extract_stream_url(info)

            if not stream_url:
                logger.warning(LogTemplates.YTDLP_NO_STREAM_URL, title)
                return None

            track_id = _generate_track_id(url, title)

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
            logger.exception(LogTemplates.YTDLP_FAILED_INFO_TO_TRACK)
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
    def _parse_info(data: dict[str, Any]) -> YtDlpTrackInfo:
        """Parse a raw yt-dlp info dict into a typed model.

        Extra fields are dropped by the model's ``extra="ignore"`` config,
        replacing the old ``_trim_info`` approach.
        """
        return YtDlpTrackInfo.model_validate(data)

    def _extract_info_sync(self, url: str) -> YtDlpTrackInfo | None:
        now = time.time()
        cached = _info_cache.get(url)
        if cached is not None:
            if now - cached.cached_at < CACHE_TTL:
                logger.debug(LogTemplates.CACHE_HIT_URL, url[:60])
                return cached.info
            _info_cache.pop(url, None)

        try:
            with YoutubeDL(params=cast(Any, self._get_opts().model_dump())) as ydl:
                data = ydl.extract_info(url, download=False)
                result = self._parse_info(dict(data)) if isinstance(data, dict) else None

                _info_cache[url] = CacheEntry(info=result, cached_at=now)

                if len(_info_cache) > 500:
                    expired = [
                        k
                        for k, entry in _info_cache.items()
                        if now - entry.cached_at >= CACHE_TTL
                    ]
                    for k in expired:
                        _info_cache.pop(k, None)
                    if expired:
                        logger.debug(LogTemplates.CACHE_EXPIRED_CLEANED, len(expired))

                return result
        except Exception:
            logger.exception(LogTemplates.YTDLP_FAILED_EXTRACT_INFO, url)
            return None

    def _search_sync(self, query: str, limit: int = 1) -> list[YtDlpTrackInfo]:
        try:
            search_query = f"ytsearch{limit}:{query}"
            with YoutubeDL(params=cast(Any, self._get_opts().model_dump())) as ydl:
                data = ydl.extract_info(search_query, download=False)

                if not isinstance(data, dict):
                    return []

                entries = data.get("entries", [])
                if not isinstance(entries, list):
                    return []

                return [self._parse_info(dict(e)) for e in entries if e]
        except Exception:
            logger.exception(LogTemplates.YTDLP_FAILED_SEARCH, query)
            return []

    def _extract_playlist_sync(self, url: str) -> list[YtDlpTrackInfo]:
        try:
            with YoutubeDL(params=cast(Any, self._get_playlist_opts().model_dump())) as ydl:
                data = ydl.extract_info(url, download=False)

                if not isinstance(data, dict):
                    return []

                entries = data.get("entries", [])
                if not isinstance(entries, list):
                    return []

                return [self._parse_info(dict(e)) for e in entries if e]
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
        tracks: list[Track] = []

        # Process in batches to avoid overwhelming yt-dlp
        batch_size = 5
        for i in range(0, len(queries), batch_size):
            batch = queries[i : i + batch_size]

            try:
                async with asyncio.TaskGroup() as tg:
                    batch_tasks = [tg.create_task(self.resolve(q)) for q in batch]

                for task in batch_tasks:
                    try:
                        result = task.result()
                        if result is not None:
                            tracks.append(result)
                    except Exception as e:
                        logger.warning(LogTemplates.RESOLUTION_FAILED.format(error=e))
            except* Exception as eg:
                for exc in eg.exceptions:
                    logger.warning(LogTemplates.RESOLUTION_FAILED.format(error=exc))

            if i + batch_size < len(queries):
                await asyncio.sleep(0.5)

        return tracks

    async def search(self, query: str, limit: int = 5) -> list[Track]:
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
        try:
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
        except Exception as e:
            logger.error(LogTemplates.PLAYLIST_FAILED.format(url=url, error=e))
            return []

    def is_url(self, query: str) -> bool:
        return any(pattern.search(query) for pattern in URL_PATTERNS)

    def is_playlist(self, url: str) -> bool:
        return any(pattern.search(url) for pattern in PLAYLIST_PATTERNS)
