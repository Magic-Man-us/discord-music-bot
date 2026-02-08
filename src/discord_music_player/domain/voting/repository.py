"""Abstract base classes defining the contracts for vote session persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod

from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.voting.entities import VoteSession
from discord_music_player.domain.voting.value_objects import VoteType


class VoteSessionRepository(ABC):
    """Abstract repository for vote sessions."""

    @abstractmethod
    async def get(self, guild_id: int, vote_type: VoteType) -> VoteSession | None:
        """Retrieve an active vote session, or None if not found or expired."""
        ...

    @abstractmethod
    async def get_or_create(
        self, guild_id: int, track_id: TrackId, vote_type: VoteType, threshold: int
    ) -> VoteSession:
        """Get an existing session or create a new one; resets if the track changed."""
        ...

    @abstractmethod
    async def save(self, session: VoteSession) -> None:
        """Save a vote session."""
        ...

    @abstractmethod
    async def delete(self, guild_id: int, vote_type: VoteType) -> bool:
        """Delete a vote session."""
        ...

    @abstractmethod
    async def delete_for_guild(self, guild_id: int) -> int:
        """Delete all vote sessions for a guild."""
        ...

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Remove all expired vote sessions."""
        ...
