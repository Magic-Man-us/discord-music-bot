"""Pydantic models for tracking Discord message state per guild."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from discord_music_player.domain.shared.types import DiscordSnowflake, NonEmptyStr, UserIdField

if TYPE_CHECKING:
    from ....domain.music.entities import Track


class TrackKey(BaseModel):
    """Frozen identity key for matching a track to its Discord message."""

    model_config = ConfigDict(frozen=True)

    track_id: NonEmptyStr
    requested_by_id: UserIdField | None = None
    requested_at: datetime | None = None

    @classmethod
    def from_track(cls, track: Track) -> TrackKey:
        return cls(
            track_id=track.id.value,
            requested_by_id=track.requested_by_id,
            requested_at=track.requested_at,
        )


class TrackedMessage(BaseModel):
    """A Discord message that the bot posted for a specific track."""

    model_config = ConfigDict(frozen=True)

    channel_id: DiscordSnowflake
    message_id: DiscordSnowflake
    track_key: TrackKey

    @classmethod
    def for_track(cls, track: Track, *, channel_id: int, message_id: int) -> TrackedMessage:
        return cls(
            channel_id=channel_id,
            message_id=message_id,
            track_key=TrackKey.from_track(track),
        )


class GuildMessageState(BaseModel):
    """Mutable per-guild state tracking now-playing and queued messages."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    now_playing: TrackedMessage | None = None
    now_playing_reserved: bool = False
    queued: deque[TrackedMessage] = Field(default_factory=deque)

    def pop_matching_queued(self, track: Track) -> TrackedMessage | None:
        target = TrackKey.from_track(track)
        if not self.queued:
            return None

        found: TrackedMessage | None = None
        for tracked in self.queued:
            if tracked.track_key == target:
                found = tracked
                break

        if found is None:
            return None

        self.queued = deque(t for t in self.queued if t.track_key != target)
        return found
