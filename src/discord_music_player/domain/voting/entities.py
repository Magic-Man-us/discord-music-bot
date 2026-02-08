"""Core domain entities for the voting bounded context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from discord_music_player.domain.shared.datetime_utils import utcnow
from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.shared.messages import ErrorMessages
from discord_music_player.domain.voting.value_objects import VoteType


@dataclass(frozen=True)
class Vote:
    """Immutable value object representing a single vote."""

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
    """Aggregate tracking votes for an action on a specific track in a guild."""

    guild_id: int
    track_id: TrackId
    vote_type: VoteType
    threshold: int
    started_at: datetime = field(default_factory=utcnow)
    expires_at: datetime | None = None
    _voters: set[int] = field(default_factory=set)

    DEFAULT_EXPIRATION_MINUTES = 5

    def __post_init__(self) -> None:
        if self.guild_id <= 0:
            raise ValueError(ErrorMessages.INVALID_GUILD_ID)
        if self.threshold < 1:
            raise ValueError(ErrorMessages.INVALID_THRESHOLD)

        if self.expires_at is None:
            self.expires_at = self.started_at + timedelta(minutes=self.DEFAULT_EXPIRATION_MINUTES)

    @property
    def vote_count(self) -> int:
        return len(self._voters)

    @property
    def votes_needed(self) -> int:
        return max(0, self.threshold - self.vote_count)

    @property
    def is_threshold_met(self) -> bool:
        return self.vote_count >= self.threshold

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return utcnow() > self.expires_at

    @property
    def voters(self) -> frozenset[int]:
        return frozenset(self._voters)

    def add_vote(self, user_id: int) -> bool:
        """Add a vote. Returns True if this vote caused the threshold to be met."""
        if self.has_voted(user_id):
            return False

        self._voters.add(user_id)
        return self.is_threshold_met

    def remove_vote(self, user_id: int) -> bool:
        if user_id in self._voters:
            self._voters.remove(user_id)
            return True
        return False

    def has_voted(self, user_id: int) -> bool:
        return user_id in self._voters

    def reset(self, new_track_id: TrackId | None = None) -> None:
        """Reset the vote session, optionally for a new track."""
        self._voters.clear()
        self.started_at = utcnow()
        self.expires_at = self.started_at + timedelta(minutes=self.DEFAULT_EXPIRATION_MINUTES)
        if new_track_id is not None:
            self.track_id = new_track_id

    def extend_expiration(self, minutes: int = 5) -> None:
        self.expires_at = utcnow() + timedelta(minutes=minutes)

    def update_threshold(self, new_threshold: int) -> None:
        """Update threshold, e.g. when listeners join or leave the channel."""
        if new_threshold < 1:
            raise ValueError(ErrorMessages.INVALID_THRESHOLD)
        self.threshold = new_threshold

    def get_progress_string(self) -> str:
        return f"{self.vote_count}/{self.threshold} votes"

    @classmethod
    def create_skip_session(
        cls, guild_id: int, track_id: TrackId, listener_count: int
    ) -> VoteSession:
        """Create a skip vote session with an auto-calculated threshold."""
        from .services import VotingDomainService

        threshold = VotingDomainService.calculate_threshold(listener_count)
        return cls(
            guild_id=guild_id,
            track_id=track_id,
            vote_type=VoteType.SKIP,
            threshold=threshold,
        )
