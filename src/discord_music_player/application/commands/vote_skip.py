"""Command and handler for vote-based skipping."""

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
    model_config = ConfigDict(frozen=True, strict=True)

    guild_id: int
    user_id: int
    user_channel_id: int | None = None

    _validate_ids = DiscordValidators.snowflakes("guild_id", "user_id")


class VoteSkipResult(BaseModel):

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

    def __init__(
        self,
        *,
        session_repository: SessionRepository,
        vote_repository: VoteSessionRepository,
        voice_adapter: VoiceAdapter,
    ) -> None:
        self._session_repo = session_repository
        self._vote_repository = vote_repository
        self._voice_adapter = voice_adapter

    async def handle(self, command: VoteSkipCommand) -> VoteSkipResult:
        from ...domain.voting.services import VotingDomainService

        session = await self._session_repo.get(command.guild_id)
        if session is None or session.current_track is None:
            return VoteSkipResult.from_vote_result(VoteResult.NO_PLAYING)

        if command.user_channel_id is None:
            return VoteSkipResult.from_vote_result(VoteResult.NOT_IN_CHANNEL)

        listeners = await self._voice_adapter.get_listeners(command.guild_id)
        listener_count = len(listeners)

        if command.user_id not in listeners:
            return VoteSkipResult.from_vote_result(VoteResult.NOT_IN_CHANNEL)

        current_track = session.current_track
        track_id = current_track.id

        if VotingDomainService.can_auto_skip(command.user_id, current_track, listener_count):
            # Clear any existing vote session to prevent votes from leaking across
            # repeated plays of the same track id (e.g. loop mode).
            await self._vote_repository.delete(command.guild_id, VoteType.SKIP)
            if current_track.was_requested_by(command.user_id):
                return VoteSkipResult.from_vote_result(VoteResult.REQUESTER_SKIP)
            return VoteSkipResult.from_vote_result(VoteResult.AUTO_SKIP)

        threshold = VotingDomainService.calculate_threshold(listener_count)
        vote_session = await self._vote_repository.get_or_create(
            guild_id=command.guild_id,
            track_id=track_id,
            vote_type=VoteType.SKIP,
            threshold=threshold,
        )

        if VotingDomainService.should_reset_session(vote_session, track_id):
            vote_session.reset(track_id)
            vote_session.update_threshold(threshold)

        vote_result, vote_session = VotingDomainService.evaluate_vote(
            session=vote_session,
            user_id=command.user_id,
            track=current_track,
            listener_count=listener_count,
            user_in_channel=True,
        )

        # Clear completed vote sessions to avoid state leaking to subsequent tracks.
        if vote_result.action_executed:
            await self._vote_repository.delete(command.guild_id, VoteType.SKIP)
        else:
            await self._vote_repository.save(vote_session)

        return VoteSkipResult.from_vote_result(
            vote_result,
            votes_current=vote_session.vote_count,
            votes_needed=vote_session.threshold,
        )
