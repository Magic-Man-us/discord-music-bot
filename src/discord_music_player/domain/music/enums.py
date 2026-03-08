"""StrEnum types for the music bounded context."""

from __future__ import annotations

from enum import StrEnum


class PlaybackState(StrEnum):
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


class LoopMode(StrEnum):
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
