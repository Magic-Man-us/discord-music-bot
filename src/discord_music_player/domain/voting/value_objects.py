"""
Voting Domain Value Objects

Immutable value objects for the voting bounded context.
"""

from enum import Enum


class VoteType(Enum):
    """Types of votes that can be cast."""

    SKIP = "skip"  # Vote to skip the current track
    STOP = "stop"  # Vote to stop playback entirely
    CLEAR = "clear"  # Vote to clear the queue

    @property
    def past_tense(self) -> str:
        """Get the past tense form for display."""
        return {
            VoteType.SKIP: "skipped",
            VoteType.STOP: "stopped",
            VoteType.CLEAR: "cleared",
        }[self]

    @property
    def action_verb(self) -> str:
        """Get the action verb for display."""
        return {
            VoteType.SKIP: "skip",
            VoteType.STOP: "stop",
            VoteType.CLEAR: "clear",
        }[self]


class VoteResult(Enum):
    """Results of attempting to cast a vote.

    These results indicate what happened when a user tried to vote.
    """

    # Successful outcomes
    VOTE_RECORDED = "vote_recorded"  # Vote was counted
    THRESHOLD_MET = "threshold_met"  # Vote hit threshold, action executed
    REQUESTER_SKIP = "requester_skip"  # Requester skipped their own track
    AUTO_SKIP = "auto_skip"  # 2-listener rule triggered auto-skip

    # Vote not counted outcomes
    ALREADY_VOTED = "already_voted"  # User already voted
    NO_PLAYING = "no_playing"  # Nothing is playing
    NOT_IN_CHANNEL = "not_in_channel"  # User not in voice channel
    BOT_NOT_IN_CHANNEL = "bot_not_in_channel"  # Bot not in voice channel

    # Error outcomes
    VOTE_EXPIRED = "vote_expired"  # Vote session expired
    INVALID_VOTE = "invalid_vote"  # Invalid vote state

    @property
    def is_success(self) -> bool:
        """Check if this result indicates a successful outcome."""
        return self in {
            VoteResult.VOTE_RECORDED,
            VoteResult.THRESHOLD_MET,
            VoteResult.REQUESTER_SKIP,
            VoteResult.AUTO_SKIP,
        }

    @property
    def action_executed(self) -> bool:
        """Check if this result means the voted action was executed."""
        return self in {
            VoteResult.THRESHOLD_MET,
            VoteResult.REQUESTER_SKIP,
            VoteResult.AUTO_SKIP,
        }

    def get_message(self, vote_type: VoteType, votes: int = 0, needed: int = 0) -> str:
        """Get a user-friendly message for this result.

        Args:
            vote_type: The type of vote.
            votes: Current vote count.
            needed: Votes needed for threshold.

        Returns:
            User-friendly message string.
        """
        messages = {
            VoteResult.VOTE_RECORDED: f"Vote recorded! ({votes}/{needed} votes to {vote_type.action_verb})",
            VoteResult.THRESHOLD_MET: f"Vote threshold met! Track {vote_type.past_tense}.",
            VoteResult.REQUESTER_SKIP: f"Track {vote_type.past_tense} by the requester.",
            VoteResult.AUTO_SKIP: f"Auto-{vote_type.past_tense} (small audience rule).",
            VoteResult.ALREADY_VOTED: "You've already voted!",
            VoteResult.NO_PLAYING: "Nothing is currently playing.",
            VoteResult.NOT_IN_CHANNEL: "You need to be in the voice channel to vote.",
            VoteResult.BOT_NOT_IN_CHANNEL: "I'm not in a voice channel.",
            VoteResult.VOTE_EXPIRED: "The voting session has expired.",
            VoteResult.INVALID_VOTE: "Invalid vote.",
        }
        return messages.get(self, "Unknown vote result.")
