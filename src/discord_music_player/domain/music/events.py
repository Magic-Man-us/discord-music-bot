"""
Music Domain Events

Domain events for the music bounded context.
These events represent significant occurrences within the domain
and are used for decoupled communication between components.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field

from discord_music_player.domain.shared.datetime_utils import utcnow

if TYPE_CHECKING:
    from .entities import Track


class MusicEvent(BaseModel):
    """Base class for all music domain events."""

    model_config = {"frozen": True}


class TrackQueued(MusicEvent):
    """Event raised when a track is added to the queue."""

    event_type: Literal["TrackQueued"] = "TrackQueued"
    guild_id: int
    track_id: str
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
            track_id=str(track.id),
            track_title=track.title,
            position=position,
            requested_by_id=track.requested_by_id,
            requested_by_name=track.requested_by_name,
        )


class TrackStarted(MusicEvent):
    """Event raised when a track starts playing."""

    event_type: Literal["TrackStarted"] = "TrackStarted"
    guild_id: int
    track_id: str
    track_title: str
    duration_seconds: int | None = None
    requested_by_id: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)

    @classmethod
    def from_track(cls, guild_id: int, track: Track) -> TrackStarted:
        """Create event from a Track entity."""
        return cls(
            guild_id=guild_id,
            track_id=str(track.id),
            track_title=track.title,
            duration_seconds=track.duration_seconds,
            requested_by_id=track.requested_by_id,
        )


class TrackFinished(MusicEvent):
    """Event raised when a track finishes playing."""

    event_type: Literal["TrackFinished"] = "TrackFinished"
    guild_id: int
    track_id: str
    track_title: str
    reason: str = "completed"  # completed, skipped, stopped, error
    timestamp: datetime = Field(default_factory=utcnow)

    @classmethod
    def from_track(cls, guild_id: int, track: Track, reason: str = "completed") -> TrackFinished:
        """Create event from a Track entity."""
        return cls(
            guild_id=guild_id,
            track_id=str(track.id),
            track_title=track.title,
            reason=reason,
        )


class TrackSkipped(MusicEvent):
    """Event raised when a track is skipped."""

    event_type: Literal["TrackSkipped"] = "TrackSkipped"
    guild_id: int
    track_id: str
    track_title: str
    skipped_by_id: int | None = None
    skip_reason: str = "user_request"  # user_request, vote, auto_skip
    timestamp: datetime = Field(default_factory=utcnow)

    @classmethod
    def from_track(
        cls,
        guild_id: int,
        track: Track,
        skipped_by_id: int | None = None,
        skip_reason: str = "user_request",
    ) -> TrackSkipped:
        """Create event from a Track entity."""
        return cls(
            guild_id=guild_id,
            track_id=str(track.id),
            track_title=track.title,
            skipped_by_id=skipped_by_id,
            skip_reason=skip_reason,
        )


class QueueCleared(MusicEvent):
    """Event raised when the queue is cleared."""

    event_type: Literal["QueueCleared"] = "QueueCleared"
    guild_id: int
    tracks_cleared: int = 0
    cleared_by_id: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)


class PlaybackPaused(MusicEvent):
    """Event raised when playback is paused."""

    event_type: Literal["PlaybackPaused"] = "PlaybackPaused"
    guild_id: int
    track_id: str | None = None
    paused_by_id: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)


class PlaybackResumed(MusicEvent):
    """Event raised when playback is resumed."""

    event_type: Literal["PlaybackResumed"] = "PlaybackResumed"
    guild_id: int
    track_id: str | None = None
    resumed_by_id: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)


class PlaybackStopped(MusicEvent):
    """Event raised when playback is stopped."""

    event_type: Literal["PlaybackStopped"] = "PlaybackStopped"
    guild_id: int
    stopped_by_id: int | None = None
    reason: str = "user_request"  # user_request, no_more_tracks, error, disconnect
    timestamp: datetime = Field(default_factory=utcnow)


class SessionCreated(MusicEvent):
    """Event raised when a new guild session is created."""

    event_type: Literal["SessionCreated"] = "SessionCreated"
    guild_id: int
    timestamp: datetime = Field(default_factory=utcnow)


class SessionDestroyed(MusicEvent):
    """Event raised when a guild session is destroyed/cleaned up."""

    event_type: Literal["SessionDestroyed"] = "SessionDestroyed"
    guild_id: int
    reason: str = "cleanup"  # cleanup, disconnect, inactivity
    timestamp: datetime = Field(default_factory=utcnow)


class VoiceChannelJoined(MusicEvent):
    """Event raised when the bot joins a voice channel."""

    event_type: Literal["VoiceChannelJoined"] = "VoiceChannelJoined"
    guild_id: int
    channel_id: int
    timestamp: datetime = Field(default_factory=utcnow)


class VoiceChannelLeft(MusicEvent):
    """Event raised when the bot leaves a voice channel."""

    event_type: Literal["VoiceChannelLeft"] = "VoiceChannelLeft"
    guild_id: int
    channel_id: int
    reason: str = "disconnect"  # disconnect, moved, kicked
    timestamp: datetime = Field(default_factory=utcnow)


class LoopModeChanged(MusicEvent):
    """Event raised when loop mode is changed."""

    event_type: Literal["LoopModeChanged"] = "LoopModeChanged"
    guild_id: int
    old_mode: str
    new_mode: str
    changed_by_id: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)


class QueueShuffled(MusicEvent):
    """Event raised when the queue is shuffled."""

    event_type: Literal["QueueShuffled"] = "QueueShuffled"
    guild_id: int
    queue_length: int
    shuffled_by_id: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)


# Discriminated union of all domain events
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
