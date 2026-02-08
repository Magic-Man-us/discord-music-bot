"""Abstract repository interfaces for music domain persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.value_objects import TrackId


class SessionRepository(ABC):
    """Abstract repository for guild playback sessions."""

    @abstractmethod
    async def get(self, guild_id: int) -> GuildPlaybackSession | None:
        """Retrieve a session by guild ID."""
        ...

    @abstractmethod
    async def get_or_create(self, guild_id: int) -> GuildPlaybackSession:
        """Get an existing session or create a new one."""
        ...

    @abstractmethod
    async def save(self, session: GuildPlaybackSession) -> None:
        """Save a session."""
        ...

    @abstractmethod
    async def delete(self, guild_id: int) -> bool:
        """Delete a session by guild ID."""
        ...

    @abstractmethod
    async def exists(self, guild_id: int) -> bool:
        """Check if a session exists for a guild."""
        ...

    @abstractmethod
    async def get_all_active(self) -> list[GuildPlaybackSession]:
        """Get all active sessions."""
        ...

    @abstractmethod
    async def cleanup_stale(self, older_than: datetime) -> int:
        """Remove sessions with no activity since the given time to prevent memory leaks."""
        ...

    @abstractmethod
    async def count(self) -> int:
        """Get the total number of sessions."""
        ...


class TrackHistoryRepository(ABC):
    """Abstract repository for track play history."""

    @abstractmethod
    async def record_play(
        self, guild_id: int, track: Track, played_at: datetime | None = None
    ) -> None:
        """Record that a track was played."""
        ...

    @abstractmethod
    async def get_recent(self, guild_id: int, limit: int = 10) -> list[Track]:
        """Get recently played tracks for a guild, most recent first."""
        ...

    @abstractmethod
    async def get_play_count(self, guild_id: int, track_id: TrackId) -> int:
        """Get the number of times a track has been played in a guild."""
        ...

    @abstractmethod
    async def get_most_played(self, guild_id: int, limit: int = 10) -> list[tuple[Track, int]]:
        """Get the most played tracks for a guild, sorted by play count descending."""
        ...

    @abstractmethod
    async def clear_history(self, guild_id: int) -> int:
        """Clear all history for a guild."""
        ...

    @abstractmethod
    async def mark_finished(
        self,
        guild_id: int,
        track_id: TrackId,
        skipped: bool = False,
    ) -> None:
        """Mark the most recent play of a track as finished."""
        ...

    @abstractmethod
    async def cleanup_old(self, older_than: datetime) -> int:
        """Remove history entries older than the given time."""
        ...
