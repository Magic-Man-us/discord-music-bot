"""Core domain entities for the voting bounded context."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from ..music.wrappers import TrackId
from ..shared.datetime_utils import utcnow
from ..shared.mixins import ExpirableMixin
from ..shared.types import DiscordSnowflake, PositiveInt
from .enums import VoteType


class Vote(BaseModel):
    """Immutable value object representing a single vote."""

    model_config = ConfigDict(frozen=True)

    user_id: DiscordSnowflake
    vote_type: VoteType
    timestamp: datetime = Field(default_factory=utcnow)

    def __hash__(self) -> int:
        return hash((self.user_id, self.vote_type))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vote):
            return NotImplemented
        return self.user_id == other.user_id and self.vote_type == other.vote_type


class VoteSession(ExpirableMixin, BaseModel):
    """Mutable aggregate tracking votes for an action on a specific track in a guild.

    ``_voters`` is a private attribute (not serialized) that tracks which
    users have voted.  Pass ``initial_voters`` at construction time to
    hydrate from persistence.
    """

    model_config = ConfigDict()

    guild_id: DiscordSnowflake
    track_id: TrackId
    vote_type: VoteType
    threshold: PositiveInt
    started_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None
    initial_voters: set[int] = Field(default_factory=set, exclude=True)

    _voters: set[int] = PrivateAttr(default_factory=set)

    DEFAULT_EXPIRATION_MINUTES: ClassVar[int] = 5

    def model_post_init(self, _context: Any) -> None:
        """Hydrate _voters from the initial_voters construction parameter."""
        self._voters = set(self.initial_voters)

    @model_validator(mode="before")
    @classmethod
    def _set_default_expires_at(cls, data: Any) -> Any:
        """Set default expiration when not explicitly provided."""
        if isinstance(data, dict) and data.get("expires_at") is None:
            started_at = data.get("started_at") or utcnow()
            data["expires_at"] = started_at + timedelta(minutes=cls.DEFAULT_EXPIRATION_MINUTES)
        return data

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
            raise ValueError("Threshold must be at least 1")
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
