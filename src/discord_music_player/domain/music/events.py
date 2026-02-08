"""Domain events for the music bounded context."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field

from discord_music_player.domain.shared.datetime_utils import utcnow

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
    guild_id: int
    track_id: TrackIdField
    track_title: str
    position: int
    requested_by_id: int | None = None
    requested_by_name: str | None = None
    timestamp: datetime = Field(default_factory=utcnow)

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
    guild_id: int
    track_id: TrackIdField
    track_title: str
    duration_seconds: int | None = None
    requested_by_id: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)

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
    guild_id: int
    track_id: TrackIdField
    track_title: str
    reason: TrackFinishReason = TrackFinishReason.COMPLETED
    timestamp: datetime = Field(default_factory=utcnow)

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
    guild_id: int
    track_id: TrackIdField
    track_title: str
    skipped_by_id: int | None = None
    skip_reason: SkipReason = SkipReason.USER_REQUEST
    timestamp: datetime = Field(default_factory=utcnow)

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
    guild_id: int
    tracks_cleared: int = 0
    cleared_by_id: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)


class PlaybackPaused(MusicEvent):
    event_type: Literal["PlaybackPaused"] = "PlaybackPaused"
    guild_id: int
    track_id: OptionalTrackIdField = None
    paused_by_id: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)


class PlaybackResumed(MusicEvent):
    event_type: Literal["PlaybackResumed"] = "PlaybackResumed"
    guild_id: int
    track_id: OptionalTrackIdField = None
    resumed_by_id: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)


class PlaybackStopped(MusicEvent):
    event_type: Literal["PlaybackStopped"] = "PlaybackStopped"
    guild_id: int
    stopped_by_id: int | None = None
    reason: StopReason = StopReason.USER_REQUEST
    timestamp: datetime = Field(default_factory=utcnow)


class SessionCreated(MusicEvent):
    event_type: Literal["SessionCreated"] = "SessionCreated"
    guild_id: int
    timestamp: datetime = Field(default_factory=utcnow)


class SessionDestroyed(MusicEvent):
    event_type: Literal["SessionDestroyed"] = "SessionDestroyed"
    guild_id: int
    reason: SessionDestroyReason = SessionDestroyReason.CLEANUP
    timestamp: datetime = Field(default_factory=utcnow)


class VoiceChannelJoined(MusicEvent):
    event_type: Literal["VoiceChannelJoined"] = "VoiceChannelJoined"
    guild_id: int
    channel_id: int
    timestamp: datetime = Field(default_factory=utcnow)


class VoiceChannelLeft(MusicEvent):
    event_type: Literal["VoiceChannelLeft"] = "VoiceChannelLeft"
    guild_id: int
    channel_id: int
    reason: VoiceLeaveReason = VoiceLeaveReason.DISCONNECT
    timestamp: datetime = Field(default_factory=utcnow)


class LoopModeChanged(MusicEvent):
    event_type: Literal["LoopModeChanged"] = "LoopModeChanged"
    guild_id: int
    old_mode: str
    new_mode: str
    changed_by_id: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)


class QueueShuffled(MusicEvent):
    event_type: Literal["QueueShuffled"] = "QueueShuffled"
    guild_id: int
    queue_length: int
    shuffled_by_id: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)


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
