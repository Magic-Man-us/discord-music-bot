"""
Music Domain Repository Interfaces

Abstract base classes defining the contracts for data persistence.
Implementations live in the infrastructure layer.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track


class SessionRepository(ABC):
    """Abstract repository for guild playback sessions.

    This repository manages the persistence of GuildPlaybackSession aggregates.
    Implementations may use in-memory storage, SQLite, Redis, etc.
    """

    @abstractmethod
    async def get(self, guild_id: int) -> GuildPlaybackSession | None:
        """Retrieve a session by guild ID.

        Args:
            guild_id: The Discord guild ID.

        Returns:
            The session if found, None otherwise.
        """
        ...

    @abstractmethod
    async def get_or_create(self, guild_id: int) -> GuildPlaybackSession:
        """Get an existing session or create a new one.

        Args:
            guild_id: The Discord guild ID.

        Returns:
            The existing or newly created session.
        """
        ...

    @abstractmethod
    async def save(self, session: GuildPlaybackSession) -> None:
        """Save a session.

        Args:
            session: The session to save.
        """
        ...

    @abstractmethod
    async def delete(self, guild_id: int) -> bool:
        """Delete a session by guild ID.

        Args:
            guild_id: The Discord guild ID.

        Returns:
            True if the session was deleted, False if it didn't exist.
        """
        ...

    @abstractmethod
    async def exists(self, guild_id: int) -> bool:
        """Check if a session exists for a guild.

        Args:
            guild_id: The Discord guild ID.

        Returns:
            True if session exists.
        """
        ...

    @abstractmethod
    async def get_all_active(self) -> list[GuildPlaybackSession]:
        """Get all active sessions (sessions with activity).

        Returns:
            List of active sessions.
        """
        ...

    @abstractmethod
    async def cleanup_stale(self, older_than: datetime) -> int:
        """Clean up sessions that haven't had activity since the given time.

        This is critical for fixing memory leaks - sessions that belong to
        guilds the bot is no longer in should be removed.

        Args:
            older_than: Remove sessions with last_activity before this time.

        Returns:
            Number of sessions cleaned up.
        """
        ...

    @abstractmethod
    async def count(self) -> int:
        """Get the total number of sessions.

        Returns:
            Total session count.
        """
        ...


class TrackHistoryRepository(ABC):
    """Abstract repository for track play history.

    This repository manages historical track data for analytics
    and recommendation features.
    """

    @abstractmethod
    async def record_play(
        self, guild_id: int, track: Track, played_at: datetime | None = None
    ) -> None:
        """Record that a track was played.

        Args:
            guild_id: The Discord guild ID.
            track: The track that was played.
            played_at: When the track was played (defaults to now).
        """
        ...

    @abstractmethod
    async def get_recent(self, guild_id: int, limit: int = 10) -> list[Track]:
        """Get recently played tracks for a guild.

        Args:
            guild_id: The Discord guild ID.
            limit: Maximum number of tracks to return.

        Returns:
            List of recently played tracks, most recent first.
        """
        ...

    @abstractmethod
    async def get_play_count(self, guild_id: int, track_id: str) -> int:
        """Get the number of times a track has been played in a guild.

        Args:
            guild_id: The Discord guild ID.
            track_id: The track identifier.

        Returns:
            Play count for the track.
        """
        ...

    @abstractmethod
    async def get_most_played(self, guild_id: int, limit: int = 10) -> list[tuple[Track, int]]:
        """Get the most played tracks for a guild.

        Args:
            guild_id: The Discord guild ID.
            limit: Maximum number of tracks to return.

        Returns:
            List of (track, play_count) tuples, sorted by play count descending.
        """
        ...

    @abstractmethod
    async def clear_history(self, guild_id: int) -> int:
        """Clear all history for a guild.

        Args:
            guild_id: The Discord guild ID.

        Returns:
            Number of history entries deleted.
        """
        ...

    @abstractmethod
    async def mark_finished(
        self,
        guild_id: int,
        track_id: str,
        skipped: bool = False,
    ) -> None:
        """Mark the most recent play of a track as finished.

        Args:
            guild_id: The Discord guild ID.
            track_id: The track identifier.
            skipped: Whether the track was skipped.
        """
        ...

    @abstractmethod
    async def cleanup_old(self, older_than: datetime) -> int:
        """Clean up history entries older than the given time.

        Args:
            older_than: Remove entries before this time.

        Returns:
            Number of entries cleaned up.
        """
        ...
