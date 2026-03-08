"""Pydantic models for SQLite row ↔ domain entity conversion.

These are infrastructure-specific models that represent the shape of database
rows.  They exist so raw ``dict`` never leaks into repository code.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.value_objects import TrackId
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

        Args:
            id_from_url: When ``True``, derive the ``TrackId`` from
                ``webpage_url`` (queue_tracks pattern).  When ``False``,
                use the stored ``track_id`` directly (track_history pattern).
        """
        track_id = TrackId.from_url(self.webpage_url) if id_from_url else TrackId(self.track_id)

        requested_at = UtcDateTime.from_iso(self.requested_at).dt if self.requested_at else None

        return Track.model_validate(
            {
                "id": track_id,
                "title": self.title,
                "webpage_url": self.webpage_url,
                "stream_url": self.stream_url,
                "duration_seconds": self.duration_seconds,
                "thumbnail_url": self.thumbnail_url,
                "artist": self.artist,
                "uploader": self.uploader,
                "like_count": self.like_count,
                "view_count": self.view_count,
                "requested_by_id": self.requested_by_id,
                "requested_by_name": self.requested_by_name,
                "requested_at": requested_at,
            }
        )


def track_to_queue_params(
    track: Track, guild_id: int, position: int, *, is_current: bool
) -> tuple[object, ...]:
    """Serialize a domain Track into a tuple for ``queue_tracks`` INSERT."""
    return (
        guild_id,
        track.id.value,
        track.title,
        track.webpage_url,
        track.stream_url,
        track.duration_seconds,
        track.thumbnail_url,
        track.artist,
        track.uploader,
        track.like_count,
        track.view_count,
        track.requested_by_id,
        track.requested_by_name,
        UtcDateTime(track.requested_at).iso if track.requested_at else None,
        position,
        is_current,
    )
