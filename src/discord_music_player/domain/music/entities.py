"""Core domain entities for the music bounded context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

from discord_music_player.domain.music.value_objects import (
    LoopMode,
    PlaybackState,
    QueuePosition,
    TrackId,
)
from discord_music_player.domain.shared.datetime_utils import utcnow
from discord_music_player.domain.shared.exceptions import (
    BusinessRuleViolationError,
    InvalidOperationError,
)
from discord_music_player.domain.shared.messages import ErrorMessages


class Track(BaseModel):
    """Immutable value object representing a playable track."""

    model_config = ConfigDict(frozen=True, strict=True)

    id: TrackId
    title: str
    webpage_url: str
    stream_url: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None

    # Track metadata (resolver-provided)
    artist: str | None = None
    uploader: str | None = None
    like_count: int | None = None
    view_count: int | None = None

    # Request metadata (set when queued)
    requested_by_id: int | None = None
    requested_by_name: str | None = None
    requested_at: datetime | None = None

    # Playback metadata
    is_from_recommendation: bool = False

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate title is not empty."""
        if not v:
            raise ValueError(ErrorMessages.EMPTY_TRACK_TITLE)
        return v

    @field_validator("webpage_url")
    @classmethod
    def validate_webpage_url(cls, v: str) -> str:
        """Validate webpage URL is not empty."""
        if not v:
            raise ValueError(ErrorMessages.EMPTY_TRACK_URL)
        return v

    @property
    def duration_formatted(self) -> str:
        """Format duration as MM:SS or HH:MM:SS."""
        if self.duration_seconds is None:
            return "Unknown"

        hours, remainder = divmod(self.duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @property
    def display_title(self) -> str:
        """Get display title with duration if available."""
        if self.duration_seconds:
            return f"{self.title} [{self.duration_formatted}]"
        return self.title

    def with_requester(
        self, user_id: int, user_name: str, requested_at: datetime | None = None
    ) -> Track:
        """Return a copy of this track with requester metadata populated."""
        return self.model_copy(
            update={
                "requested_by_id": user_id,
                "requested_by_name": user_name,
                "requested_at": requested_at or utcnow(),
            }
        )

    def was_requested_by(self, user_id: int) -> bool:
        return self.requested_by_id == user_id


@dataclass
class GuildPlaybackSession:
    """Aggregate root managing playback state for a single Discord guild."""

    MAX_QUEUE_SIZE: ClassVar[int] = 50

    guild_id: int
    queue: list[Track] = field(default_factory=list)
    current_track: Track | None = None
    state: PlaybackState = PlaybackState.IDLE
    loop_mode: LoopMode = LoopMode.OFF
    created_at: datetime = field(default_factory=utcnow)
    last_activity: datetime = field(default_factory=utcnow)

    # Version for optimistic concurrency
    version: int = 0

    def __post_init__(self) -> None:
        if self.guild_id <= 0:
            raise ValueError(ErrorMessages.INVALID_GUILD_ID)

    @property
    def queue_length(self) -> int:
        return len(self.queue)

    @property
    def is_playing(self) -> bool:
        return self.state == PlaybackState.PLAYING

    @property
    def is_paused(self) -> bool:
        return self.state == PlaybackState.PAUSED

    @property
    def is_idle(self) -> bool:
        return self.state == PlaybackState.IDLE

    @property
    def has_tracks(self) -> bool:
        return self.current_track is not None or bool(self.queue)

    @property
    def can_add_to_queue(self) -> bool:
        return self.queue_length < self.MAX_QUEUE_SIZE

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = utcnow()

    def enqueue(self, track: Track) -> QueuePosition:
        """Add a track to the end of the queue."""
        if not self.can_add_to_queue:
            raise BusinessRuleViolationError(
                rule="MAX_QUEUE_SIZE", message=f"Queue is full (max {self.MAX_QUEUE_SIZE} tracks)"
            )

        position = QueuePosition(len(self.queue))
        self.queue.append(track)
        self.touch()
        return position

    def enqueue_next(self, track: Track) -> QueuePosition:
        """Add a track to the front of the queue (play next)."""
        if not self.can_add_to_queue:
            raise BusinessRuleViolationError(
                rule="MAX_QUEUE_SIZE", message=f"Queue is full (max {self.MAX_QUEUE_SIZE} tracks)"
            )

        self.queue.insert(0, track)
        self.touch()
        return QueuePosition(0)

    def dequeue(self) -> Track | None:
        """Remove and return the next track from the queue."""
        if not self.queue:
            return None

        track = self.queue.pop(0)
        self.touch()
        return track

    def peek(self) -> Track | None:
        """Look at the next track without removing it."""
        return self.queue[0] if self.queue else None

    def remove_at(self, position: int) -> Track | None:
        """Remove a track at a specific queue position."""
        if 0 <= position < len(self.queue):
            track = self.queue.pop(position)
            self.touch()
            return track
        return None

    def clear_queue(self) -> int:
        """Clear all tracks from the queue and return the count removed."""
        count = len(self.queue)
        self.queue.clear()
        self.touch()
        return count

    def set_current_track(self, track: Track | None) -> None:
        """Set the currently playing track."""
        self.current_track = track
        self.touch()

    def transition_to(self, new_state: PlaybackState) -> None:
        """Transition to a new playback state."""
        if not self.state.can_transition_to(new_state):
            raise InvalidOperationError(
                operation=f"transition to {new_state.value}",
                current_state=self.state.value,
                message=f"Cannot transition from {self.state.value} to {new_state.value}",
            )

        self.state = new_state
        self.touch()

    def start_playback(self, track: Track) -> None:
        """Start playing a track."""
        self.current_track = track
        if self.state == PlaybackState.IDLE or self.state == PlaybackState.STOPPED:
            self.state = PlaybackState.PLAYING
        self.touch()

    def pause(self) -> None:
        """Pause playback."""
        self.transition_to(PlaybackState.PAUSED)

    def resume(self) -> None:
        """Resume playback."""
        self.transition_to(PlaybackState.PLAYING)

    def stop(self) -> None:
        """Stop playback completely."""
        self.state = PlaybackState.STOPPED
        self.current_track = None
        self.touch()

    def reset(self) -> None:
        """Reset session to idle state."""
        self.state = PlaybackState.IDLE
        self.current_track = None
        self.queue.clear()
        self.touch()

    def advance_to_next_track(self) -> Track | None:
        """Advance to the next track based on loop mode."""
        if self.loop_mode == LoopMode.TRACK and self.current_track:
            return self.current_track

        if self.loop_mode == LoopMode.QUEUE and self.current_track:
            self.queue.append(self.current_track)

        next_track = self.dequeue()
        self.current_track = next_track

        if next_track is None:
            self.state = PlaybackState.IDLE

        return next_track

    def toggle_loop(self) -> LoopMode:
        """Toggle loop mode and return the new mode."""
        self.loop_mode = self.loop_mode.next_mode()
        self.touch()
        return self.loop_mode

    def shuffle(self) -> None:
        """Shuffle the queue."""
        import random

        random.shuffle(self.queue)
        self.touch()

    def move_track(self, from_pos: int, to_pos: int) -> bool:
        """Move a track from one queue position to another."""
        if not (0 <= from_pos < len(self.queue) and 0 <= to_pos < len(self.queue)):
            return False

        track = self.queue.pop(from_pos)
        self.queue.insert(to_pos, track)
        self.touch()
        return True
