"""Pydantic models for SQLite row ↔ domain entity conversion.

These are infrastructure-specific models that represent the shape of database
rows.  They exist so raw ``dict`` never leaks into repository code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.domain.shared.datetime_utils import UtcDateTime
from discord_music_player.domain.shared.types import (
    DiscordSnowflake,
    DurationSeconds,
    HttpUrlStr,
    NonEmptyStr,
    NonNegativeInt,
)


class TrackRow(BaseModel):
    """Typed representation of a track row from ``queue_tracks`` or ``track_history``.

    Covers the superset of columns across both tables.  Missing columns
    (e.g. ``stream_url`` in history) default to ``None``.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    track_id: NonEmptyStr
    title: NonEmptyStr
    webpage_url: HttpUrlStr
    stream_url: HttpUrlStr | None = None
    duration_seconds: DurationSeconds | None = None
    thumbnail_url: HttpUrlStr | None = None
    artist: NonEmptyStr | None = None
    uploader: NonEmptyStr | None = None
    like_count: NonNegativeInt | None = None
    view_count: NonNegativeInt | None = None
    requested_by_id: DiscordSnowflake | None = None
    requested_by_name: NonEmptyStr | None = None
    requested_at: str | None = None

    def to_track(self, *, id_from_url: bool = False) -> Track:
        """Convert to a domain ``Track``.

        Field coercions (``track_id`` str → ``TrackId``, ``requested_at``
        ISO string → ``datetime``) are handled by ``Track``'s own
        ``field_validator``s.

        Args:
            id_from_url: When ``True``, derive the ``TrackId`` from
                ``webpage_url`` (queue_tracks pattern).  When ``False``,
                use the stored ``track_id`` directly (track_history pattern).
        """
        data = self.model_dump()
        track_id_str = data.pop("track_id")
        data["id"] = TrackId.from_url(self.webpage_url) if id_from_url else track_id_str
        return Track.model_validate(data)


class QueueTrackRow(BaseModel):
    """INSERT-ready representation of a track in the ``queue_tracks`` table.

    Constructed from a domain ``Track`` via :meth:`from_track`.
    Serialized to a named-parameter dict via ``model_dump()``.
    """

    model_config = ConfigDict(frozen=True)

    guild_id: DiscordSnowflake
    track_id: NonEmptyStr
    title: NonEmptyStr
    webpage_url: HttpUrlStr
    stream_url: HttpUrlStr | None = None
    duration_seconds: DurationSeconds | None = None
    thumbnail_url: HttpUrlStr | None = None
    artist: NonEmptyStr | None = None
    uploader: NonEmptyStr | None = None
    like_count: NonNegativeInt | None = None
    view_count: NonNegativeInt | None = None
    requested_by_id: DiscordSnowflake | None = None
    requested_by_name: NonEmptyStr | None = None
    requested_at: str | None = None
    position: int
    is_current: bool

    @field_validator("track_id", mode="before")
    @classmethod
    def _flatten_track_id(cls, v: Any) -> str:
        """Accept a TrackId value object or its dict dump and extract the string."""
        if isinstance(v, TrackId):
            return v.value
        if isinstance(v, dict):
            return v.get("value", v)
        return v

    @field_validator("requested_at", mode="before")
    @classmethod
    def _datetime_to_iso(cls, v: Any) -> str | None:
        """Accept a datetime and convert to ISO string for SQLite storage."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return UtcDateTime(v).iso
        return v

    @classmethod
    def from_track(
        cls,
        track: Track,
        *,
        guild_id: DiscordSnowflake,
        position: int,
        is_current: bool,
    ) -> QueueTrackRow:
        """Build from a domain Track plus queue metadata.

        The ``id`` → ``track_id`` rename and ``datetime`` → ISO conversion
        are handled by field validators automatically.
        """
        return cls.model_validate(
            {
                **track.model_dump(exclude={"is_from_recommendation"}),
                "track_id": track.id,
                "guild_id": guild_id,
                "position": position,
                "is_current": is_current,
            }
        )


# ── SQL for QueueTrackRow inserts ─────────────────────────────────────

QUEUE_TRACKS_INSERT_SQL: str = """
    INSERT INTO queue_tracks (
        guild_id, track_id, title, webpage_url, stream_url,
        duration_seconds, thumbnail_url, artist, uploader,
        like_count, view_count, requested_by_id, requested_by_name,
        requested_at, position, is_current
    ) VALUES (
        :guild_id, :track_id, :title, :webpage_url, :stream_url,
        :duration_seconds, :thumbnail_url, :artist, :uploader,
        :like_count, :view_count, :requested_by_id, :requested_by_name,
        :requested_at, :position, :is_current
    )
"""
