"""Reusable Pydantic Annotated types for domain-wide validation.

Every constrained type used across bounded contexts is defined here once,
so models can simply annotate their fields::

    from discord_music_player.domain.shared.types import DiscordSnowflake, NonEmptyStr

    class MyModel(BaseModel):
        guild_id: DiscordSnowflake
        name: NonEmptyStr
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

T = TypeVar("T")


# ── Generic single-field wrapper ───────────────────────────────────

class ValueWrapper(BaseModel, Generic[T]):
    """Generic base for single-field frozen value objects.

    Construct with ``TrackId(value="abc")``.  Provides hashing, equality,
    and str/int conversions.
    """

    model_config = ConfigDict(frozen=True)

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

DiscordSnowflake = Annotated[int, Field(gt=0, lt=2**64)]
"""Positive integer that fits a Discord snowflake (1 … 2^64-1)."""

NonNegativeInt = Annotated[int, Field(ge=0)]
"""Integer >= 0."""

PositiveInt = Annotated[int, Field(gt=0)]
"""Integer > 0."""

NonNegativeFloat = Annotated[float, Field(ge=0.0)]
"""Float >= 0.0."""

UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]
"""Float in [0.0, 1.0] — used for confidence scores."""

PercentageInt = Annotated[int, Field(ge=0, le=100)]
"""Integer percentage: 0 … 100."""

VolumeFloat = Annotated[float, Field(ge=0.0, le=2.0)]
"""Audio volume multiplier in [0.0, 2.0]."""


# ── String constraints ──────────────────────────────────────────────

NonEmptyStr = Annotated[str, Field(min_length=1)]
"""String with at least one character."""

TrackTitleStr = Annotated[str, Field(min_length=1, max_length=500)]
"""Track title: 1-500 characters."""

HttpUrlStr = Annotated[str, Field(pattern=r"^https?://")]
"""String that starts with http:// or https://."""


# ── File size constraints ──────────────────────────────────────────

FileBytes = Annotated[int, Field(ge=0)]
"""File size in bytes: >= 0."""

FileSizeMB = Annotated[float, Field(ge=0.0)]
"""File size in megabytes: >= 0.0."""

BYTES_PER_MB: int = 1024 * 1024
"""1 mebibyte = 1 048 576 bytes."""


# ── Domain-specific numeric constraints ─────────────────────────────

DurationSeconds = Annotated[int, Field(ge=0, le=86_400)]
"""Track duration in seconds: 0 … 86 400 (24 hours)."""

QueuePositionInt = Annotated[int, Field(ge=0)]
"""Zero-based queue position."""


# ── Settings-specific constraints ──────────────────────────────────

PoolSize = Annotated[int, Field(ge=1, le=100)]
"""Database connection pool size: 1 … 100."""

BusyTimeoutMs = Annotated[int, Field(ge=1000, le=30000)]
"""Database busy timeout in milliseconds: 1 000 … 30 000."""

ConnectionTimeoutS = Annotated[int, Field(ge=1, le=60)]
"""Database connection timeout in seconds: 1 … 60."""

CommandPrefixStr = Annotated[str, Field(min_length=1, max_length=5)]
"""Bot command prefix: 1-5 characters."""

MaxQueueSize = Annotated[int, Field(gt=0, le=1000)]
"""Maximum queue size: 1 … 1 000."""

MaxTokens = Annotated[int, Field(ge=1, le=4096)]
"""AI max tokens: 1 … 4 096."""

TemperatureFloat = Annotated[float, Field(ge=0.0, le=2.0)]
"""AI temperature: 0.0 … 2.0."""

RadioCount = Annotated[int, Field(gt=0, le=10)]
"""Radio visible tracks in queue: 1 … 10."""

RadioBatchSize = Annotated[int, Field(gt=0, le=10)]
"""Radio AI batch size: 1 … 10 (capped by MAX_RECOMMENDATION_COUNT)."""

RadioMaxTracks = Annotated[int, Field(gt=0, le=200)]
"""Radio max tracks per session: 1 … 200."""


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


# ── Genre classification types ─────────────────────────────────────

class TrackForClassification(BaseModel):
    """A track to be classified by the genre classifier."""

    model_config = ConfigDict(frozen=True)

    track_id: NonEmptyStr
    description: str | None = None

TrackGenreMap = dict[NonEmptyStr, NonEmptyStr]
"""Mapping of track_id → genre name, as returned by the AI classifier and stored in the DB."""
