"""Immutable value objects for the music bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from pydantic import PlainSerializer, PlainValidator

from discord_music_player.domain.shared.messages import ErrorMessages


@dataclass(frozen=True)
class TrackId:
    """Typically a YouTube video ID or a hash of the URL."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError(ErrorMessages.EMPTY_TRACK_ID)

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    @classmethod
    def from_url(cls, url: str) -> TrackId:
        """Extract track ID from a URL, using YouTube video ID or a URL hash as fallback."""
        import hashlib
        import re

        youtube_patterns = [
            r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
            r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        ]

        for pattern in youtube_patterns:
            match = re.search(pattern, url)
            if match:
                return cls(match.group(1))

        url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
        return cls(url_hash)


# Pydantic-compatible type aliases for TrackId fields.
# Serializes as plain string in JSON, stores as TrackId in the model.
TrackIdField = Annotated[
    TrackId,
    PlainValidator(lambda v: TrackId(v) if isinstance(v, str) else v),
    PlainSerializer(lambda v: v.value, return_type=str),
]

OptionalTrackIdField = Annotated[
    TrackId | None,
    PlainValidator(lambda v: TrackId(v) if isinstance(v, str) else v),
    PlainSerializer(lambda v: v.value if v is not None else None, return_type=str | None),
]


@dataclass(frozen=True)
class QueuePosition:
    """Value object for queue positioning."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(ErrorMessages.INVALID_QUEUE_POSITION)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value

    def next(self) -> QueuePosition:
        """Return the next position in queue."""
        return QueuePosition(self.value + 1)

    def previous(self) -> QueuePosition:
        """Return the previous position in queue (minimum 0)."""
        return QueuePosition(max(0, self.value - 1))


@dataclass(frozen=True)
class StartSeconds:
    """Validated seek offset for starting playback at a specific timestamp."""

    value: int

    def __post_init__(self) -> None:
        from ..shared.constants import AudioConstants

        if self.value < 0:
            raise ValueError("Start seconds cannot be negative")
        if self.value > AudioConstants.MAX_SEEK_SECONDS:
            raise ValueError(
                f"Start seconds cannot exceed {AudioConstants.MAX_SEEK_SECONDS}"
            )

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.value)

    @classmethod
    def from_optional(cls, seconds: int | None) -> StartSeconds | None:
        """Create from an optional int, returning None if input is None or zero."""
        if not seconds:
            return None
        return cls(seconds)


class PlaybackState(Enum):
    """Playback state with enforced transitions.

    State transitions:
    - IDLE -> PLAYING (start playback)
    - PLAYING -> PAUSED (pause)
    - PAUSED -> PLAYING (resume)
    - PLAYING -> STOPPED (stop command or error)
    - PAUSED -> STOPPED (stop command)
    - STOPPED -> IDLE (reset)
    - Any -> IDLE (disconnect/cleanup)
    """

    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"

    def can_transition_to(self, target: PlaybackState) -> bool:
        """Check if transition to target state is valid."""
        valid_transitions = {
            PlaybackState.IDLE: {PlaybackState.PLAYING},
            PlaybackState.PLAYING: {
                PlaybackState.PAUSED,
                PlaybackState.STOPPED,
                PlaybackState.IDLE,
            },
            PlaybackState.PAUSED: {
                PlaybackState.PLAYING,
                PlaybackState.STOPPED,
                PlaybackState.IDLE,
            },
            PlaybackState.STOPPED: {PlaybackState.IDLE, PlaybackState.PLAYING},
        }
        return target in valid_transitions.get(self, set())

    @property
    def is_active(self) -> bool:
        return self in {PlaybackState.PLAYING, PlaybackState.PAUSED}

    @property
    def is_playing(self) -> bool:
        return self == PlaybackState.PLAYING

    @property
    def can_accept_commands(self) -> bool:
        return self != PlaybackState.STOPPED


class TrackFinishReason(Enum):
    """Reasons a track can finish playing."""

    COMPLETED = "completed"
    SKIPPED = "skipped"
    STOPPED = "stopped"
    ERROR = "error"


class SkipReason(Enum):
    """Reasons a track can be skipped."""

    USER_REQUEST = "user_request"
    VOTE = "vote"
    AUTO_SKIP = "auto_skip"


class StopReason(Enum):
    """Reasons playback can be stopped."""

    USER_REQUEST = "user_request"
    NO_MORE_TRACKS = "no_more_tracks"
    ERROR = "error"
    DISCONNECT = "disconnect"


class SessionDestroyReason(Enum):
    """Reasons a session can be destroyed."""

    CLEANUP = "cleanup"
    DISCONNECT = "disconnect"
    INACTIVITY = "inactivity"


class VoiceLeaveReason(Enum):
    """Reasons the bot can leave a voice channel."""

    DISCONNECT = "disconnect"
    MOVED = "moved"
    KICKED = "kicked"


class LoopMode(Enum):
    """Loop mode settings for queue playback."""

    OFF = "off"
    TRACK = "track"  # Loop current track
    QUEUE = "queue"  # Loop entire queue

    def next_mode(self) -> LoopMode:
        """Cycle to next loop mode."""
        modes = list(LoopMode)
        current_index = modes.index(self)
        next_index = (current_index + 1) % len(modes)
        return modes[next_index]
