"""
Vote Skip Command

Command and handler for vote-based skipping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from discord_music_player.domain.shared.validators import DiscordValidators
from discord_music_player.domain.voting.value_objects import VoteResult, VoteType

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository
    from ...domain.voting.repository import VoteSessionRepository
    from ..interfaces.voice_adapter import VoiceAdapter


class VoteSkipCommand(BaseModel):
    """Command to cast a vote to skip the current track."""

    model_config = ConfigDict(frozen=True, strict=True)

    guild_id: int
    user_id: int
    user_channel_id: int | None = None

    # Validate Discord snowflake IDs using reusable validators
    _validate_ids = DiscordValidators.snowflakes("guild_id", "user_id")


class VoteSkipResult(BaseModel):
    """Result of a vote skip command."""

    model_config = ConfigDict(frozen=True, strict=True)

    result: VoteResult
    message: str
    votes_current: int = 0
    votes_needed: int = 0
    action_executed: bool = False

    @property
    def is_success(self) -> bool:
        return self.result.is_success

    @classmethod
    def from_vote_result(
        cls,
        result: VoteResult,
        votes_current: int = 0,
        votes_needed: int = 0,
    ) -> VoteSkipResult:
        message = result.get_message(VoteType.SKIP, votes_current, votes_needed)
        return cls(
            result=result,
            message=message,
            votes_current=votes_current,
            votes_needed=votes_needed,
            action_executed=result.action_executed,
        )


class VoteSkipHandler:
    """Handler for VoteSkipCommand."""

    def __init__(
        self,
        session_repository: SessionRepository,
        vote_repository: VoteSessionRepository,
        voice_adapter: VoiceAdapter,
    ) -> None:
        self._session_repository = session_repository
        self._vote_repository = vote_repository
        self._voice_adapter = voice_adapter

    async def handle(self, command: VoteSkipCommand) -> VoteSkipResult:
        """Execute the vote skip command."""
        from ...domain.voting.services import VotingDomainService

        # Check if something is playing
        session = await self._session_repository.get(command.guild_id)
        if session is None or session.current_track is None:
            return VoteSkipResult.from_vote_result(VoteResult.NO_PLAYING)

        # Check if user is in voice channel
        if command.user_channel_id is None:
            return VoteSkipResult.from_vote_result(VoteResult.NOT_IN_CHANNEL)

        # Get listener count
        listeners = await self._voice_adapter.get_listeners(command.guild_id)
        listener_count = len(listeners)

        # Check if user is in the bot's channel
        if command.user_id not in listeners:
            return VoteSkipResult.from_vote_result(VoteResult.NOT_IN_CHANNEL)

        current_track = session.current_track
        track_id = str(current_track.id)

        # Check for auto-skip conditions
        if VotingDomainService.can_auto_skip(command.user_id, current_track, listener_count):
            # If we're auto-skipping, clear any existing skip-vote session.
            # This prevents votes from leaking across repeated plays of the same
            # track id (e.g., loop mode) and keeps the repository consistent.
            await self._vote_repository.delete(command.guild_id, VoteType.SKIP)
            # Execute skip
            if current_track.was_requested_by(command.user_id):
                return VoteSkipResult.from_vote_result(VoteResult.REQUESTER_SKIP)
            return VoteSkipResult.from_vote_result(VoteResult.AUTO_SKIP)

        # Get or create vote session
        threshold = VotingDomainService.calculate_threshold(listener_count)
        vote_session = await self._vote_repository.get_or_create(
            guild_id=command.guild_id,
            track_id=track_id,
            vote_type=VoteType.SKIP,
            threshold=threshold,
        )

        # Reset if track changed
        if VotingDomainService.should_reset_session(vote_session, track_id):
            vote_session.reset(track_id)
            vote_session.update_threshold(threshold)

        # Evaluate and add vote
        vote_result, vote_session = VotingDomainService.evaluate_vote(
            session=vote_session,
            user_id=command.user_id,
            track=current_track,
            listener_count=listener_count,
            user_in_channel=True,
        )

        # Persist vote session.
        # If the action is considered executed (threshold met), clear the
        # session immediately to avoid vote state leaking to subsequent tracks
        # (or repeated track ids).
        if vote_result.action_executed:
            await self._vote_repository.delete(command.guild_id, VoteType.SKIP)
        else:
            await self._vote_repository.save(vote_session)

        return VoteSkipResult.from_vote_result(
            vote_result,
            votes_current=vote_session.vote_count,
            votes_needed=vote_session.threshold,
        )
