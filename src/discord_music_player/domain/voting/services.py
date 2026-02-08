"""
Voting Domain Services

Domain services containing voting business logic.
"""

from typing import TYPE_CHECKING

from discord_music_player.domain.voting.entities import VoteSession
from discord_music_player.domain.voting.value_objects import VoteResult

if TYPE_CHECKING:
    from ..music.entities import Track


class VotingDomainService:
    """Domain service for voting-related business rules.

    Encapsulates voting logic including threshold calculations,
    auto-skip rules, and vote evaluation.
    """

    # Configuration constants
    MINIMUM_THRESHOLD = 1
    SMALL_AUDIENCE_SIZE = 2  # If <= this many listeners, requester can skip

    @classmethod
    def calculate_threshold(cls, listener_count: int) -> int:
        """Calculate the vote threshold based on listener count.

        Uses a majority vote rule: more than half of listeners must vote.
        Minimum threshold is 1.

        Args:
            listener_count: Number of listeners in the voice channel
                           (excluding the bot).

        Returns:
            The number of votes required to pass.
        """
        if listener_count <= 0:
            return cls.MINIMUM_THRESHOLD

        # More than half must vote
        threshold = (listener_count // 2) + 1
        return max(cls.MINIMUM_THRESHOLD, threshold)

    @classmethod
    def can_auto_skip(cls, user_id: int, track: "Track", listener_count: int) -> bool:
        """Check if a user can auto-skip without voting.

        Auto-skip is allowed when:
        1. The user is the one who requested the track, OR
        2. There are very few listeners (small audience rule)

        Args:
            user_id: The ID of the user trying to skip.
            track: The current track.
            listener_count: Number of listeners in the channel.

        Returns:
            True if the user can skip without voting.
        """
        # Requester can always skip their own track
        if track.was_requested_by(user_id):
            return True

        # Small audience rule: if only 1-2 listeners, anyone can skip
        if listener_count <= cls.SMALL_AUDIENCE_SIZE:
            return True

        return False

    @classmethod
    def evaluate_vote(
        cls,
        session: VoteSession,
        user_id: int,
        track: "Track | None" = None,
        listener_count: int = 0,
        user_in_channel: bool = True,
    ) -> tuple[VoteResult, VoteSession]:
        """Evaluate a vote and return the result.

        This method handles all vote validation and processing logic.

        Args:
            session: The current vote session.
            user_id: The ID of the user voting.
            track: The current track (for auto-skip check).
            listener_count: Number of listeners (for auto-skip check).
            user_in_channel: Whether the user is in the voice channel.

        Returns:
            Tuple of (VoteResult, updated VoteSession).
        """
        # Check preconditions
        if not user_in_channel:
            return VoteResult.NOT_IN_CHANNEL, session

        if session.is_expired:
            return VoteResult.VOTE_EXPIRED, session

        # Check for auto-skip conditions
        if track is not None and listener_count > 0:
            if track.was_requested_by(user_id):
                return VoteResult.REQUESTER_SKIP, session

            if listener_count <= cls.SMALL_AUDIENCE_SIZE:
                return VoteResult.AUTO_SKIP, session

        # Check if already voted
        if session.has_voted(user_id):
            return VoteResult.ALREADY_VOTED, session

        # Cast the vote
        threshold_met = session.add_vote(user_id)

        if threshold_met:
            return VoteResult.THRESHOLD_MET, session

        return VoteResult.VOTE_RECORDED, session

    @classmethod
    def should_reset_session(cls, session: VoteSession, current_track_id: str) -> bool:
        """Check if a vote session should be reset.

        Sessions should be reset when the track changes.

        Args:
            session: The vote session.
            current_track_id: The ID of the currently playing track.

        Returns:
            True if the session should be reset.
        """
        return session.track_id != current_track_id or session.is_expired

    @classmethod
    def create_response_message(cls, result: VoteResult, session: VoteSession) -> str:
        """Create a user-friendly response message for a vote result.

        Args:
            result: The vote result.
            session: The vote session.

        Returns:
            A formatted message string.
        """
        return result.get_message(
            vote_type=session.vote_type, votes=session.vote_count, needed=session.threshold
        )


class VoteResultHandler:
    """Handles the outcomes of vote results.

    This class determines what actions should be taken based on
    vote results.
    """

    @staticmethod
    def should_execute_action(result: VoteResult) -> bool:
        """Check if the voted action should be executed.

        Args:
            result: The vote result.

        Returns:
            True if the action (skip, stop, etc.) should be executed.
        """
        return result.action_executed

    @staticmethod
    def should_notify_progress(result: VoteResult) -> bool:
        """Check if vote progress should be communicated.

        Args:
            result: The vote result.

        Returns:
            True if a progress message should be sent.
        """
        return result == VoteResult.VOTE_RECORDED

    @staticmethod
    def should_notify_failure(result: VoteResult) -> bool:
        """Check if a failure message should be sent.

        Args:
            result: The vote result.

        Returns:
            True if an error/failure message should be sent.
        """
        return result in {
            VoteResult.ALREADY_VOTED,
            VoteResult.NOT_IN_CHANNEL,
            VoteResult.BOT_NOT_IN_CHANNEL,
            VoteResult.NO_PLAYING,
            VoteResult.VOTE_EXPIRED,
        }
