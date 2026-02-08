"""
Voting Domain Repository Interfaces

Abstract base classes defining the contracts for vote session persistence.
"""

from abc import ABC, abstractmethod

from discord_music_player.domain.voting.entities import VoteSession
from discord_music_player.domain.voting.value_objects import VoteType


class VoteSessionRepository(ABC):
    """Abstract repository for vote sessions.

    Vote sessions are typically short-lived and may be stored in-memory,
    but this interface allows for persistent storage if needed.
    """

    @abstractmethod
    async def get(self, guild_id: int, vote_type: VoteType) -> VoteSession | None:
        """Retrieve an active vote session.

        Args:
            guild_id: The Discord guild ID.
            vote_type: The type of vote session to retrieve.

        Returns:
            The vote session if found and not expired, None otherwise.
        """
        ...

    @abstractmethod
    async def get_or_create(
        self, guild_id: int, track_id: str, vote_type: VoteType, threshold: int
    ) -> VoteSession:
        """Get an existing vote session or create a new one.

        If the existing session is for a different track, it will be
        reset with the new track ID.

        Args:
            guild_id: The Discord guild ID.
            track_id: The ID of the current track.
            vote_type: The type of vote session.
            threshold: The vote threshold.

        Returns:
            The existing or newly created vote session.
        """
        ...

    @abstractmethod
    async def save(self, session: VoteSession) -> None:
        """Save a vote session.

        Args:
            session: The vote session to save.
        """
        ...

    @abstractmethod
    async def delete(self, guild_id: int, vote_type: VoteType) -> bool:
        """Delete a vote session.

        Args:
            guild_id: The Discord guild ID.
            vote_type: The type of vote session to delete.

        Returns:
            True if a session was deleted.
        """
        ...

    @abstractmethod
    async def delete_for_guild(self, guild_id: int) -> int:
        """Delete all vote sessions for a guild.

        Args:
            guild_id: The Discord guild ID.

        Returns:
            Number of sessions deleted.
        """
        ...

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Clean up all expired vote sessions.

        Returns:
            Number of sessions cleaned up.
        """
        ...
