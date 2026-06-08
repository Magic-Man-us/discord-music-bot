"""Pydantic models for yt-dlp data transformation and configuration.

These are infrastructure-specific models for parsing external yt-dlp data,
caching extraction results, and configuring yt-dlp options.
"""

from __future__ import annotations

from typing import Annotated, Any, Final

from pydantic import (
    BaseModel,
    Discriminator,
    Field,
    Tag,
    TypeAdapter,
    field_serializer,
    field_validator,
)

from ...domain.shared.enums import YtDlpJsRuntime
from ...domain.shared.model_config import FrozenBoundaryModelConfig, FrozenModelConfig
from ...domain.shared.types import (
    HttpHeaders,
    HttpUrlStr,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    OptionalHttpUrlStr,
    OptionalNonEmptyStr,
    PositiveInt,
)

# ── Annotated list types ──────────────────────────────────────────────

NonEmptyStrList = Annotated[list[NonEmptyStr], Field(min_length=1)]
"""List of non-empty strings with at least one element."""

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
EXTRACT_TIMEOUT: Final[int] = 30  # seconds — max time for a single yt-dlp extraction


# ── Pydantic models for yt-dlp data ────────────────────────────────────


class AudioFormatInfo(BaseModel):
    """A single audio format entry from yt-dlp extraction."""

    model_config = FrozenBoundaryModelConfig

    url: NonEmptyStr | None = None
    acodec: NonEmptyStr | None = None


class YtDlpTrackInfo(BaseModel):
    """Trimmed yt-dlp extraction result for caching and track conversion.

    Extra fields from yt-dlp are silently ignored, keeping memory usage low.
    Before-validators coerce garbage from external yt-dlp data gracefully.
    """

    model_config = FrozenBoundaryModelConfig

    webpage_url: OptionalHttpUrlStr = None
    url: OptionalNonEmptyStr = None
    title: NonEmptyStr = "Unknown Title"
    duration: NonNegativeInt | None = None
    thumbnail: OptionalHttpUrlStr = None
    artist: OptionalNonEmptyStr = None
    creator: OptionalNonEmptyStr = None
    uploader: OptionalNonEmptyStr = None
    channel: OptionalNonEmptyStr = None
    like_count: NonNegativeInt | None = None
    view_count: NonNegativeInt | None = None
    formats: list[AudioFormatInfo] = Field(default_factory=list)
    http_headers: HttpHeaders | None = None

    @field_validator("title", mode="before")
    @classmethod
    def _coerce_title(cls, v: Any) -> str:
        """Fall back to default when yt-dlp sends empty or non-string title."""
        if not isinstance(v, str) or not v.strip():
            return "Unknown Title"
        return v

    @field_validator("like_count", "view_count", "duration", mode="before")
    @classmethod
    def _coerce_nonneg_int(cls, v: Any) -> int | None:
        """Coerce to non-negative int; return None for garbage values."""
        if v is None:
            return None
        try:
            val = int(v)
            return val if val >= 0 else None
        except (TypeError, ValueError):
            return None


class YtDlpExtractResult(BaseModel):
    """Top-level yt-dlp extraction result (search or playlist).

    Wraps the raw dict returned by ``YoutubeDL.extract_info`` for
    multi-entry results, parsing each entry into a ``YtDlpTrackInfo``.
    Invalid entries are silently dropped.
    """

    model_config = FrozenBoundaryModelConfig

    entries: list[YtDlpTrackInfo] = Field(default_factory=list)
    title: OptionalNonEmptyStr = None

    @field_validator("entries", mode="before")
    @classmethod
    def _coerce_entries(cls, v: Any) -> list[YtDlpTrackInfo]:
        """Parse each raw dict into YtDlpTrackInfo, dropping invalid entries."""
        if not isinstance(v, list):
            return []
        parsed: list[YtDlpTrackInfo] = []
        for e in v:
            if not isinstance(e, dict):
                continue
            try:
                parsed.append(YtDlpTrackInfo.model_validate(e))
            except Exception:
                continue
        return parsed


def _ytdlp_result_kind(value: Any) -> str:
    """Discriminator: classify a raw yt-dlp ``extract_info`` result by its ``_type``."""
    if isinstance(value, YtDlpExtractResult):
        return "playlist"
    if isinstance(value, YtDlpTrackInfo):
        return "video"
    if isinstance(value, dict) and (value.get("_type") == "playlist" or "entries" in value):
        return "playlist"
    return "video"


YtDlpResult = Annotated[
    Annotated[YtDlpTrackInfo, Tag("video")] | Annotated[YtDlpExtractResult, Tag("playlist")],
    Discriminator(_ytdlp_result_kind),
]
"""A yt-dlp ``extract_info`` result: a single ``video`` or a ``playlist``, by ``_type``."""

YTDLP_RESULT_ADAPTER: Final = TypeAdapter(YtDlpResult)


class CacheEntry(BaseModel):
    """Cached yt-dlp extraction result with expiry timestamp."""

    model_config = FrozenModelConfig

    info: YtDlpTrackInfo | None = None
    cached_at: NonNegativeFloat


# ── yt-dlp option models ───────────────────────────────────────────────


class YouTubeExtractorConfig(BaseModel):
    """YouTube-specific yt-dlp extractor arguments."""

    model_config = FrozenModelConfig

    pot_server_url: HttpUrlStr
    player_client: NonEmptyStrList


class ExtractorArgs(BaseModel):
    """Container for yt-dlp extractor arguments."""

    model_config = FrozenModelConfig

    youtube: YouTubeExtractorConfig


class JsRuntimeConfig(BaseModel):
    """Per-runtime entry for yt-dlp's ``js_runtimes`` param; ``path`` locates the binary."""

    model_config = FrozenModelConfig

    path: NonEmptyStr | None = None


JsRuntimeMap = dict[YtDlpJsRuntime, JsRuntimeConfig]
"""yt-dlp ``js_runtimes`` mapping: runtime → its config."""

JsRuntimeWire = dict[str, dict[str, str | None]]
"""Serialized ``js_runtimes`` as yt-dlp expects it: ``{"node": {"path": "/..."}}``."""


class YtDlpOpts(BaseModel):
    """Typed yt-dlp configuration options passed to YoutubeDL."""

    model_config = FrozenModelConfig

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
    js_runtimes: JsRuntimeMap = Field(
        default_factory=lambda: {YtDlpJsRuntime.NODE: JsRuntimeConfig()}
    )

    @field_serializer("js_runtimes")
    def _serialize_js_runtimes(self, value: JsRuntimeMap) -> JsRuntimeWire:
        # yt-dlp expects plain string keys: {"node": {"path": "/..."}}
        return {runtime.value: config.model_dump() for runtime, config in value.items()}
