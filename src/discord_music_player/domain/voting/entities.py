"""
Voting Domain Entities

Core domain entities for the voting bounded context.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from discord_music_player.domain.shared.datetime_utils import utcnow
from discord_music_player.domain.shared.messages import ErrorMessages

from discord_music_player.domain.voting.value_objects import VoteType


@dataclass(frozen=True)
class Vote:
    """Value object representing a single vote.

    Votes are immutable - once cast, they cannot be changed.
    """

    user_id: int
    vote_type: VoteType
    timestamp: datetime = field(default_factory=utcnow)

    def __hash__(self) -> int:
        return hash((self.user_id, self.vote_type))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vote):
            return NotImplemented
        return self.user_id == other.user_id and self.vote_type == other.vote_type


@dataclass
class VoteSession:
    """Aggregate for a voting session.

    A VoteSession tracks votes for a specific action (skip, stop, etc.)
    on a specific track in a guild.
    """

    guild_id: int
    track_id: str
    vote_type: VoteType
    threshold: int
    started_at: datetime = field(default_factory=utcnow)
    expires_at: datetime | None = None
    _voters: set[int] = field(default_factory=set)

    # Default expiration time
    DEFAULT_EXPIRATION_MINUTES = 5

    def __post_init__(self) -> None:
        if self.guild_id <= 0:
            raise ValueError(ErrorMessages.INVALID_GUILD_ID)
        if self.threshold < 1:
            raise ValueError(ErrorMessages.INVALID_THRESHOLD)

        # Set default expiration if not provided
        if self.expires_at is None:
            self.expires_at = self.started_at + timedelta(minutes=self.DEFAULT_EXPIRATION_MINUTES)

    @property
    def vote_count(self) -> int:
        """Get the current number of votes."""
        return len(self._voters)

    @property
    def votes_needed(self) -> int:
        """Get the number of additional votes needed to reach threshold."""
        return max(0, self.threshold - self.vote_count)

    @property
    def is_threshold_met(self) -> bool:
        """Check if the vote threshold has been met."""
        return self.vote_count >= self.threshold

    @property
    def is_expired(self) -> bool:
        """Check if the vote session has expired."""
        if self.expires_at is None:
            return False
        return utcnow() > self.expires_at

    @property
    def voters(self) -> frozenset[int]:
        """Get immutable set of voter IDs."""
        return frozenset(self._voters)

    def add_vote(self, user_id: int) -> bool:
        """Add a vote from a user.

        Args:
            user_id: The ID of the user voting.

        Returns:
            True if this vote caused the threshold to be met.
        """
        if self.has_voted(user_id):
            return False

        self._voters.add(user_id)
        return self.is_threshold_met

    def remove_vote(self, user_id: int) -> bool:
        """Remove a vote from a user.

        Args:
            user_id: The ID of the user whose vote to remove.

        Returns:
            True if a vote was removed.
        """
        if user_id in self._voters:
            self._voters.remove(user_id)
            return True
        return False

    def has_voted(self, user_id: int) -> bool:
        """Check if a user has already voted.

        Args:
            user_id: The ID of the user to check.

        Returns:
            True if the user has already voted.
        """
        return user_id in self._voters

    def reset(self, new_track_id: str | None = None) -> None:
        """Reset the vote session for a new track.

        Args:
            new_track_id: Optional new track ID. If None, uses existing.
        """
        self._voters.clear()
        self.started_at = utcnow()
        self.expires_at = self.started_at + timedelta(minutes=self.DEFAULT_EXPIRATION_MINUTES)
        if new_track_id is not None:
            # Note: We need to use object.__setattr__ because track_id might
            # be used as part of the identity. But since we're using dataclass
            # without frozen=True, we can assign directly
            self.track_id = new_track_id

    def extend_expiration(self, minutes: int = 5) -> None:
        """Extend the vote session expiration.

        Args:
            minutes: Number of minutes to extend by.
        """
        self.expires_at = utcnow() + timedelta(minutes=minutes)

    def update_threshold(self, new_threshold: int) -> None:
        """Update the vote threshold.

        This might be needed when listeners join or leave the channel.

        Args:
            new_threshold: The new threshold value.
        """
        if new_threshold < 1:
            raise ValueError(ErrorMessages.INVALID_THRESHOLD)
        self.threshold = new_threshold

    def get_progress_string(self) -> str:
        """Get a string representation of voting progress.

        Returns:
            String like "3/5 votes".
        """
        return f"{self.vote_count}/{self.threshold} votes"

    @classmethod
    def create_skip_session(
        cls, guild_id: int, track_id: str, listener_count: int
    ) -> "VoteSession":
        """Factory method to create a skip vote session.

        Args:
            guild_id: The Discord guild ID.
            track_id: The ID of the track being voted on.
            listener_count: Number of listeners in the voice channel.

        Returns:
            A new VoteSession configured for skip voting.
        """
        from .services import VotingDomainService

        threshold = VotingDomainService.calculate_threshold(listener_count)
        return cls(
            guild_id=guild_id,
            track_id=track_id,
            vote_type=VoteType.SKIP,
            threshold=threshold,
        )
