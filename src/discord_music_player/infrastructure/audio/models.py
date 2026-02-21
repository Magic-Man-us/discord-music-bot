"""Pydantic models for yt-dlp data transformation and configuration.

These are infrastructure-specific models for parsing external yt-dlp data,
caching extraction results, and configuring yt-dlp options.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from discord_music_player.domain.shared.types import (
    HttpUrlStr,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
)

CACHE_TTL: Final[int] = 3600
CACHE_MAX_SIZE: Final[int] = 500
DEFAULT_RETRIES: Final[int] = 3
DEFAULT_SOCKET_TIMEOUT: Final[int] = 10
DEFAULT_HTTP_CHUNK_SIZE: Final[int] = 1024 * 1024  # 1 MiB
DEFAULT_SEARCH_LIMIT: Final[int] = 5
HASH_ID_LENGTH: Final[int] = 16
LOG_URL_TRUNCATE: Final[int] = 60
RESOLVE_BATCH_SIZE: Final[int] = 5
RESOLVE_BATCH_DELAY: Final[float] = 0.5


# ── Pydantic models for yt-dlp data ────────────────────────────────────


class AudioFormatInfo(BaseModel):
    """A single audio format entry from yt-dlp extraction."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    url: NonEmptyStr | None = None
    acodec: NonEmptyStr | None = None


class YtDlpTrackInfo(BaseModel):
    """Trimmed yt-dlp extraction result for caching and track conversion.

    Extra fields from yt-dlp are silently ignored, keeping memory usage low.
    Before-validators coerce garbage from external yt-dlp data gracefully.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    webpage_url: HttpUrlStr | None = None
    url: NonEmptyStr | None = None
    title: NonEmptyStr = "Unknown Title"
    duration: NonNegativeInt | None = None
    thumbnail: HttpUrlStr | None = None
    artist: NonEmptyStr | None = None
    creator: NonEmptyStr | None = None
    uploader: NonEmptyStr | None = None
    channel: NonEmptyStr | None = None
    like_count: NonNegativeInt | None = None
    view_count: NonNegativeInt | None = None
    formats: list[AudioFormatInfo] = Field(default_factory=list)

    @field_validator(
        "webpage_url", "url", "thumbnail",
        "artist", "creator", "uploader", "channel",
        mode="before",
    )
    @classmethod
    def _coerce_empty_to_none(cls, v: Any) -> str | None:
        """Convert empty / whitespace-only / non-string values to None."""
        if not isinstance(v, str) or not v.strip():
            return None
        return v

    @field_validator("title", mode="before")
    @classmethod
    def _coerce_title(cls, v: Any) -> str:
        """Fall back to default when yt-dlp sends empty or non-string title."""
        if not isinstance(v, str) or not v.strip():
            return "Unknown Title"
        return v

    @field_validator("like_count", "view_count", mode="before")
    @classmethod
    def _coerce_count(cls, v: Any) -> int | None:
        """Coerce to non-negative int; return None for garbage values."""
        if v is None:
            return None
        try:
            val = int(v)
            return val if val >= 0 else None
        except (TypeError, ValueError):
            return None

    @field_validator("duration", mode="before")
    @classmethod
    def _coerce_duration(cls, v: Any) -> int | None:
        """Coerce to non-negative int; return None for garbage values."""
        if v is None:
            return None
        try:
            val = int(v)
            return val if val >= 0 else None
        except (TypeError, ValueError):
            return None


class CacheEntry(BaseModel):
    """Cached yt-dlp extraction result with expiry timestamp."""

    model_config = ConfigDict(frozen=True)

    info: YtDlpTrackInfo | None = None
    cached_at: NonNegativeFloat


# ── yt-dlp option models ───────────────────────────────────────────────


class YouTubeExtractorConfig(BaseModel):
    """YouTube-specific yt-dlp extractor arguments."""

    model_config = ConfigDict(frozen=True)

    pot_server_url: HttpUrlStr
    player_client: list[NonEmptyStr] = Field(
        default_factory=lambda: ["android", "web"], min_length=1,
    )


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
    default_search: NonEmptyStr = "ytsearch"
    forceipv4: bool = True
    retries: PositiveInt = DEFAULT_RETRIES
    socket_timeout: PositiveInt = DEFAULT_SOCKET_TIMEOUT
    http_chunk_size: PositiveInt = DEFAULT_HTTP_CHUNK_SIZE
    format: NonEmptyStr | None = None
    skip_download: bool = True
    extract_flat: NonEmptyStr | bool = False
    extractor_args: ExtractorArgs | None = None
