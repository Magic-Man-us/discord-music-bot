"""
Music Bounded Context

Domain logic for track playback, queue management, and session handling.
"""

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.events import (
    QueueCleared,
    TrackFinished,
    TrackQueued,
    TrackStarted,
)
from discord_music_player.domain.music.repository import SessionRepository
from discord_music_player.domain.music.services import QueueDomainService
from discord_music_player.domain.music.value_objects import PlaybackState, QueuePosition, TrackId

__all__ = [
    # Entities
    "Track",
    "GuildPlaybackSession",
    # Value Objects
    "TrackId",
    "QueuePosition",
    "PlaybackState",
    # Events
    "TrackQueued",
    "TrackStarted",
    "TrackFinished",
    "QueueCleared",
    # Repository
    "SessionRepository",
    # Services
    "QueueDomainService",
]
