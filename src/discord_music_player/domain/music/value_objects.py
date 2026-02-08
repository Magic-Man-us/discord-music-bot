"""
Music Domain Value Objects

Immutable value objects for the music bounded context.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from discord_music_player.domain.shared.messages import ErrorMessages


@dataclass(frozen=True)
class TrackId:
    """Value object for track identification.

    Typically a YouTube video ID or a hash of the URL.
    """

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
        """Extract track ID from a URL.

        For YouTube, extracts the video ID.
        For other URLs, uses a hash of the URL.
        """
        import hashlib
        import re

        # YouTube URL patterns
        youtube_patterns = [
            r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
            r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        ]

        for pattern in youtube_patterns:
            match = re.search(pattern, url)
            if match:
                return cls(match.group(1))

        # Fallback to URL hash
        url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
        return cls(url_hash)


@dataclass(frozen=True)
class QueuePosition:
    """Value object for queue positioning."""

    value: int

    def __post_init__(self) -> None:
        # Use object.__setattr__ because dataclass is frozen
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


class PlaybackState(Enum):
    """Value object representing playback states.

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
        """Check if state represents active playback."""
        return self in {PlaybackState.PLAYING, PlaybackState.PAUSED}

    @property
    def is_playing(self) -> bool:
        """Check if currently playing."""
        return self == PlaybackState.PLAYING

    @property
    def can_accept_commands(self) -> bool:
        """Check if state can accept playback commands."""
        return self != PlaybackState.STOPPED


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
