"""Domain events for the music bounded context."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field

from discord_music_player.domain.shared.datetime_utils import utcnow
from discord_music_player.domain.shared.types import (
    DiscordSnowflake,
    DurationSeconds,
    NonEmptyStr,
    NonNegativeInt,
    UtcDatetimeField,
)

from .value_objects import (
    OptionalTrackIdField,
    SessionDestroyReason,
    SkipReason,
    StopReason,
    TrackFinishReason,
    TrackIdField,
    VoiceLeaveReason,
)

if TYPE_CHECKING:
    from .entities import Track


class MusicEvent(BaseModel):
    """Base class for all music domain events."""

    model_config = {"frozen": True}


class TrackQueued(MusicEvent):
    event_type: Literal["TrackQueued"] = "TrackQueued"
    guild_id: DiscordSnowflake
    track_id: TrackIdField
    track_title: NonEmptyStr
    position: NonNegativeInt
    requested_by_id: DiscordSnowflake | None = None
    requested_by_name: NonEmptyStr | None = None
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)

    @classmethod
    def from_track(
        cls,
        guild_id: int,
        track: Track,
        position: int,
    ) -> TrackQueued:
        """Create event from a Track entity."""
        return cls(
            guild_id=guild_id,
            track_id=track.id,
            track_title=track.title,
            position=position,
            requested_by_id=track.requested_by_id,
            requested_by_name=track.requested_by_name,
        )


class TrackStarted(MusicEvent):
    event_type: Literal["TrackStarted"] = "TrackStarted"
    guild_id: DiscordSnowflake
    track_id: TrackIdField
    track_title: NonEmptyStr
    duration_seconds: DurationSeconds | None = None
    requested_by_id: DiscordSnowflake | None = None
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)

    @classmethod
    def from_track(cls, guild_id: int, track: Track) -> TrackStarted:
        """Create event from a Track entity."""
        return cls(
            guild_id=guild_id,
            track_id=track.id,
            track_title=track.title,
            duration_seconds=track.duration_seconds,
            requested_by_id=track.requested_by_id,
        )


class TrackFinished(MusicEvent):
    event_type: Literal["TrackFinished"] = "TrackFinished"
    guild_id: DiscordSnowflake
    track_id: TrackIdField
    track_title: NonEmptyStr
    reason: TrackFinishReason = TrackFinishReason.COMPLETED
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)

    @classmethod
    def from_track(
        cls, guild_id: int, track: Track, reason: TrackFinishReason = TrackFinishReason.COMPLETED
    ) -> TrackFinished:
        """Create event from a Track entity."""
        return cls(
            guild_id=guild_id,
            track_id=track.id,
            track_title=track.title,
            reason=reason,
        )


class TrackSkipped(MusicEvent):
    event_type: Literal["TrackSkipped"] = "TrackSkipped"
    guild_id: DiscordSnowflake
    track_id: TrackIdField
    track_title: NonEmptyStr
    skipped_by_id: DiscordSnowflake | None = None
    skip_reason: SkipReason = SkipReason.USER_REQUEST
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)

    @classmethod
    def from_track(
        cls,
        guild_id: int,
        track: Track,
        skipped_by_id: int | None = None,
        skip_reason: SkipReason = SkipReason.USER_REQUEST,
    ) -> TrackSkipped:
        """Create event from a Track entity."""
        return cls(
            guild_id=guild_id,
            track_id=track.id,
            track_title=track.title,
            skipped_by_id=skipped_by_id,
            skip_reason=skip_reason,
        )


class QueueCleared(MusicEvent):
    event_type: Literal["QueueCleared"] = "QueueCleared"
    guild_id: DiscordSnowflake
    tracks_cleared: NonNegativeInt = 0
    cleared_by_id: DiscordSnowflake | None = None
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)


class PlaybackPaused(MusicEvent):
    event_type: Literal["PlaybackPaused"] = "PlaybackPaused"
    guild_id: DiscordSnowflake
    track_id: OptionalTrackIdField = None
    paused_by_id: DiscordSnowflake | None = None
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)


class PlaybackResumed(MusicEvent):
    event_type: Literal["PlaybackResumed"] = "PlaybackResumed"
    guild_id: DiscordSnowflake
    track_id: OptionalTrackIdField = None
    resumed_by_id: DiscordSnowflake | None = None
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)


class PlaybackStopped(MusicEvent):
    event_type: Literal["PlaybackStopped"] = "PlaybackStopped"
    guild_id: DiscordSnowflake
    stopped_by_id: DiscordSnowflake | None = None
    reason: StopReason = StopReason.USER_REQUEST
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)


class SessionCreated(MusicEvent):
    event_type: Literal["SessionCreated"] = "SessionCreated"
    guild_id: DiscordSnowflake
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)


class SessionDestroyed(MusicEvent):
    event_type: Literal["SessionDestroyed"] = "SessionDestroyed"
    guild_id: DiscordSnowflake
    reason: SessionDestroyReason = SessionDestroyReason.CLEANUP
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)


class VoiceChannelJoined(MusicEvent):
    event_type: Literal["VoiceChannelJoined"] = "VoiceChannelJoined"
    guild_id: DiscordSnowflake
    channel_id: DiscordSnowflake
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)


class VoiceChannelLeft(MusicEvent):
    event_type: Literal["VoiceChannelLeft"] = "VoiceChannelLeft"
    guild_id: DiscordSnowflake
    channel_id: DiscordSnowflake
    reason: VoiceLeaveReason = VoiceLeaveReason.DISCONNECT
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)


class LoopModeChanged(MusicEvent):
    event_type: Literal["LoopModeChanged"] = "LoopModeChanged"
    guild_id: DiscordSnowflake
    old_mode: NonEmptyStr
    new_mode: NonEmptyStr
    changed_by_id: DiscordSnowflake | None = None
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)


class QueueShuffled(MusicEvent):
    event_type: Literal["QueueShuffled"] = "QueueShuffled"
    guild_id: DiscordSnowflake
    queue_length: NonNegativeInt
    shuffled_by_id: DiscordSnowflake | None = None
    timestamp: UtcDatetimeField = Field(default_factory=utcnow)


DomainEvent = Annotated[
    TrackQueued
    | TrackStarted
    | TrackFinished
    | TrackSkipped
    | QueueCleared
    | PlaybackPaused
    | PlaybackResumed
    | PlaybackStopped
    | SessionCreated
    | SessionDestroyed
    | VoiceChannelJoined
    | VoiceChannelLeft
    | LoopModeChanged
    | QueueShuffled,
    Field(discriminator="event_type"),
]
