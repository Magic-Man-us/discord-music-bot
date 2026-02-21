"""Domain services containing voting business logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.shared.types import DiscordSnowflake, NonNegativeInt, PositiveInt
from discord_music_player.domain.voting.entities import VoteSession
from discord_music_player.domain.voting.value_objects import VoteResult

if TYPE_CHECKING:
    from ..music.entities import Track


class VotingDomainService:
    """Voting business rules: threshold calculations, auto-skip, and vote evaluation."""

    MINIMUM_THRESHOLD = 1
    SMALL_AUDIENCE_SIZE = 2  # If <= this many listeners, anyone can skip

    @classmethod
    def calculate_threshold(cls, listener_count: NonNegativeInt) -> PositiveInt:
        """Calculate the vote threshold (majority rule: more than half must vote)."""
        if listener_count <= 0:
            return cls.MINIMUM_THRESHOLD

        threshold = (listener_count // 2) + 1
        return max(cls.MINIMUM_THRESHOLD, threshold)

    @classmethod
    def can_auto_skip(cls, user_id: DiscordSnowflake, track: Track, listener_count: NonNegativeInt) -> bool:
        """Check if a user can skip without voting (requester or small audience)."""
        if track.was_requested_by(user_id):
            return True

        if listener_count <= cls.SMALL_AUDIENCE_SIZE:
            return True

        return False

    @classmethod
    def evaluate_vote(
        cls,
        session: VoteSession,
        user_id: DiscordSnowflake,
        track: Track | None = None,
        listener_count: NonNegativeInt = 0,
        user_in_channel: bool = True,
    ) -> tuple[VoteResult, VoteSession]:
        """Evaluate a vote and return the result with the updated session."""
        if not user_in_channel:
            return VoteResult.NOT_IN_CHANNEL, session

        if session.is_expired:
            return VoteResult.VOTE_EXPIRED, session

        if track is not None and listener_count > 0:
            if track.was_requested_by(user_id):
                return VoteResult.REQUESTER_SKIP, session

            if listener_count <= cls.SMALL_AUDIENCE_SIZE:
                return VoteResult.AUTO_SKIP, session

        if session.has_voted(user_id):
            return VoteResult.ALREADY_VOTED, session

        threshold_met = session.add_vote(user_id)

        if threshold_met:
            return VoteResult.THRESHOLD_MET, session

        return VoteResult.VOTE_RECORDED, session

    @classmethod
    def should_reset_session(cls, session: VoteSession, current_track_id: TrackId) -> bool:
        """Check if a vote session should be reset (track changed or expired)."""
        return session.track_id != current_track_id or session.is_expired

    @classmethod
    def create_response_message(cls, result: VoteResult, session: VoteSession) -> str:
        return result.get_message(
            vote_type=session.vote_type, votes=session.vote_count, needed=session.threshold
        )
