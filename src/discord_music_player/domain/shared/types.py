"""Reusable Pydantic Annotated types for domain-wide validation.

Every constrained type used across bounded contexts is defined here once, carrying
its constraint and schema metadata (description / examples) in a single place::

    from discord_music_player.domain.shared.types import DiscordSnowflake, NonEmptyStr

    class MyModel(BaseModel):
        guild_id: DiscordSnowflake
        name: NonEmptyStr
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field

from .enums import YtDlpPlayerClient
from .model_config import FrozenModelConfig

# ── Generic single-field wrapper ───────────────────────────────────


class ValueWrapper[T](BaseModel):
    """Generic base for single-field frozen value objects.

    Construct with ``TrackId(value="abc")``.  Provides hashing, equality,
    and str/int conversions.
    """

    model_config = FrozenModelConfig

    value: T  # type: ignore[misc]

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return int(self.value)  # type: ignore[arg-type]

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, type(self)):
            return self.value == other.value
        return NotImplemented


# ── Numeric constraints ─────────────────────────────────────────────

DiscordSnowflake = Annotated[
    int,
    Field(
        gt=0,
        lt=2**64,
        description="Discord snowflake ID (1 .. 2^64-1).",
        examples=[123456789012345678],
    ),
]

DiscordSnowflakeTuple = tuple[DiscordSnowflake, ...]
"""Immutable sequence of Discord snowflake IDs (owners, guilds, …)."""

NonNegativeInt = Annotated[int, Field(ge=0, description="Integer >= 0.", examples=[0])]

PositiveInt = Annotated[int, Field(gt=0, description="Integer > 0.", examples=[1])]

NonNegativeFloat = Annotated[float, Field(ge=0.0, description="Float >= 0.0.", examples=[0.0])]

UnitInterval = Annotated[
    float, Field(ge=0.0, le=1.0, description="Confidence/ratio in [0.0, 1.0].", examples=[0.5])
]

PercentageInt = Annotated[
    int, Field(ge=0, le=100, description="Percentage: 0 .. 100.", examples=[42])
]

VolumeFloat = Annotated[
    float,
    Field(ge=0.0, le=2.0, description="Audio volume multiplier in [0.0, 2.0].", examples=[1.0]),
]

PrebufferSeconds = Annotated[
    float,
    Field(
        ge=0.5,
        le=30.0,
        description="Seconds of decoded audio held ahead of the send loop.",
        examples=[5.0],
    ),
]

PrefillSeconds = Annotated[
    float,
    Field(
        ge=0.0,
        le=30.0,
        description="Seconds buffered before the first frame is handed to the send loop.",
        examples=[2.0],
    ),
]

FrameCount = Annotated[
    int,
    Field(gt=0, description="Count of 20 ms PCM audio frames.", examples=[250]),
]

PrefillTimeoutSeconds = Annotated[
    float,
    Field(
        gt=0.0,
        description="Upper bound on the first read()'s wait for the prebuffer to prime.",
        examples=[7.0],
    ),
]


# ── String constraints ──────────────────────────────────────────────

NonEmptyStr = Annotated[
    str, Field(min_length=1, description="Non-empty string.", examples=["text"])
]

TrackTitleStr = Annotated[
    str,
    Field(
        min_length=1,
        max_length=500,
        description="Track title (1-500 characters).",
        examples=["Daft Punk - Get Lucky"],
    ),
]

HttpUrlStr = Annotated[
    str,
    Field(
        pattern=r"^https?://",
        description="URL starting with http:// or https://.",
        examples=["https://youtu.be/dQw4w9WgXcQ"],
    ),
]


def coerce_empty_to_none(v: Any) -> str | None:
    """Convert empty / whitespace-only / non-string values to None (boundary coercion)."""
    if not isinstance(v, str) or not v.strip():
        return None
    return v


OptionalNonEmptyStr = Annotated[NonEmptyStr | None, BeforeValidator(coerce_empty_to_none)]
"""Non-empty string that coerces empty / whitespace / non-string input to None."""

OptionalHttpUrlStr = Annotated[HttpUrlStr | None, BeforeValidator(coerce_empty_to_none)]
"""http(s) URL that coerces empty / whitespace / non-string input to None."""

HttpHeaders = dict[NonEmptyStr, str]
"""HTTP request headers (e.g. yt-dlp's per-format headers) keyed by header name."""

FfmpegOptions = dict[NonEmptyStr, str]
"""FFmpeg argument groups (e.g. ``before_options`` / ``options``) keyed by group name."""

DatabaseUrlStr = Annotated[
    str,
    Field(
        min_length=1,
        description="Database URL; the scheme is validated on the settings model.",
        examples=["sqlite:///data/bot.db"],
    ),
]

PlayerClientList = list[YtDlpPlayerClient]
"""Ordered yt-dlp ``player_client`` identifiers to try when resolving a stream."""


# ── File size constraints ──────────────────────────────────────────

FileBytes = Annotated[
    int, Field(ge=0, description="File size in bytes (>= 0).", examples=[1048576])
]

FileSizeMB = Annotated[
    float, Field(ge=0.0, description="File size in megabytes (>= 0.0).", examples=[2.5])
]

BYTES_PER_MB: int = 1024 * 1024
"""1 mebibyte = 1 048 576 bytes."""


# ── Domain-specific numeric constraints ─────────────────────────────

DurationSeconds = Annotated[
    int,
    Field(ge=0, le=86_400, description="Track duration in seconds (0 .. 86400).", examples=[210]),
]

QueuePositionInt = Annotated[
    int, Field(ge=0, description="Zero-based queue position.", examples=[0])
]

PlaylistImportCount = Annotated[
    int,
    Field(
        ge=1,
        le=50,
        description="Tracks to import from an external playlist (1 .. 50).",
        examples=[10],
    ),
]

PlaylistStartIndex = Annotated[
    int,
    Field(ge=1, le=1000, description="1-based playlist start offset (1 .. 1000).", examples=[1]),
]

FollowTrackCount = Annotated[
    int,
    Field(
        ge=1,
        le=25,
        description="Tracks to mirror before /playmine auto-stops (1 .. 25).",
        examples=[5],
    ),
]

RecommendationCount = Annotated[
    int, Field(ge=1, le=10, description="AI recommendations to request (1 .. 10).", examples=[3])
]


# ── Settings-specific constraints ──────────────────────────────────

PoolSize = Annotated[
    int, Field(ge=1, le=100, description="Database connection pool size (1 .. 100).", examples=[5])
]

BusyTimeoutMs = Annotated[
    int,
    Field(
        ge=1000,
        le=30000,
        description="Database busy timeout in ms (1000 .. 30000).",
        examples=[5000],
    ),
]

ConnectionTimeoutS = Annotated[
    int,
    Field(
        ge=1, le=60, description="Database connection timeout in seconds (1 .. 60).", examples=[10]
    ),
]

CommandPrefixStr = Annotated[
    str,
    Field(
        min_length=1,
        max_length=5,
        description="Bot command prefix (1-5 characters).",
        examples=["!"],
    ),
]

MaxQueueSize = Annotated[
    int, Field(gt=0, le=1000, description="Maximum queue size (1 .. 1000).", examples=[50])
]

MaxTokens = Annotated[
    int, Field(ge=1, le=4096, description="AI max output tokens (1 .. 4096).", examples=[500])
]

TemperatureFloat = Annotated[
    float,
    Field(ge=0.0, le=2.0, description="AI sampling temperature (0.0 .. 2.0).", examples=[0.7]),
]

RadioCount = Annotated[
    int, Field(gt=0, le=10, description="Radio visible tracks in queue (1 .. 10).", examples=[3])
]

RadioBatchSize = Annotated[
    int, Field(gt=0, le=10, description="Radio AI batch size (1 .. 10).", examples=[10])
]

RadioMaxTracks = Annotated[
    int, Field(gt=0, le=200, description="Radio max tracks per session (1 .. 200).", examples=[50])
]


# ── Datetime constraints ────────────────────────────────────────────


def _ensure_utc(v: datetime) -> datetime:
    """Validate that a datetime is timezone-aware and normalise to UTC."""
    if v.tzinfo is None:
        raise ValueError("datetime must be timezone-aware (UTC)")
    return v.astimezone(UTC)


UtcDatetimeField = Annotated[datetime, BeforeValidator(_ensure_utc)]
"""Timezone-aware datetime, normalised to UTC on input."""


# ── Pydantic-compatible ID aliases ──────────────────────────────────

UserIdField = DiscordSnowflake
"""Alias — user ID used as a plain Pydantic field."""

ChannelIdField = DiscordSnowflake
"""Alias — channel ID used as a plain Pydantic field."""
