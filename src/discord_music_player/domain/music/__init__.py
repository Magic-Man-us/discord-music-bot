"""
Music Bounded Context

Domain logic for track playback, queue management, and session handling.
"""

from .entities import GuildPlaybackSession, Track
from .enums import PlaybackState
from .repository import SessionRepository
from .wrappers import QueuePosition, TrackId

__all__ = [
    # Entities
    "Track",
    "GuildPlaybackSession",
    # Value Objects
    "TrackId",
    "QueuePosition",
    "PlaybackState",
    # Repository
    "SessionRepository",
]
