"""Voting Application Service - vote-based skip orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from ...domain.shared.types import DiscordSnowflake, NonNegativeInt
from ...domain.voting.enums import VoteResult, VoteType

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository
    from ...domain.voting.repository import VoteSessionRepository
    from ..interfaces.voice_adapter import VoiceAdapter


class VoteSkipResult(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    result: VoteResult
    message: str
    votes_current: NonNegativeInt = 0
    votes_needed: NonNegativeInt = 0
    action_executed: bool = False

    @property
    def is_success(self) -> bool:
        return self.result.is_success

    def format_display(self, track_title: str) -> str:
        return self.result.get_message(
            VoteType.SKIP,
            self.votes_current,
            self.votes_needed,
            track_title=track_title,
        )

    @classmethod
    def from_vote_result(
        cls,
        result: VoteResult,
        votes_current: int = 0,
        votes_needed: int = 0,
    ) -> VoteSkipResult:
        if not isinstance(result, VoteResult):
            raise TypeError(f"Expected VoteResult, got {type(result).__name__}: {result!r}")
        message = result.get_message(VoteType.SKIP, votes_current, votes_needed)
        return cls(
            result=result,
            message=message,
            votes_current=votes_current,
            votes_needed=votes_needed,
            action_executed=result.action_executed,
        )


class VotingApplicationService:
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

    async def vote_skip(
        self,
        *,
        guild_id: DiscordSnowflake,
        user_id: DiscordSnowflake,
        user_channel_id: DiscordSnowflake | None,
    ) -> VoteSkipResult:
        from ...domain.voting.services import VotingDomainService

        session = await self._session_repo.get(guild_id)
        if session is None or session.current_track is None:
            return VoteSkipResult.from_vote_result(VoteResult.NO_PLAYING)

        if user_channel_id is None:
            return VoteSkipResult.from_vote_result(VoteResult.NOT_IN_CHANNEL)

        listeners = await self._voice_adapter.get_listeners(guild_id)
        listener_count = len(listeners)

        if user_id not in listeners:
            return VoteSkipResult.from_vote_result(VoteResult.NOT_IN_CHANNEL)

        current_track = session.current_track
        track_id = current_track.id

        if VotingDomainService.can_auto_skip(user_id, current_track, listener_count):
            # Clear any existing vote session to prevent votes from leaking across
            # repeated plays of the same track id (e.g. loop mode).
            await self._vote_repository.delete(guild_id, VoteType.SKIP)
            if current_track.was_requested_by(user_id):
                return VoteSkipResult.from_vote_result(VoteResult.REQUESTER_SKIP)
            return VoteSkipResult.from_vote_result(VoteResult.AUTO_SKIP)

        threshold = VotingDomainService.calculate_threshold(listener_count)
        vote_session = await self._vote_repository.get_or_create(
            guild_id=guild_id,
            track_id=track_id,
            vote_type=VoteType.SKIP,
            threshold=threshold,
        )

        if VotingDomainService.should_reset_session(vote_session, track_id):
            vote_session.reset(track_id)
            vote_session.update_threshold(threshold)

        vote_result, vote_session = VotingDomainService.evaluate_vote(
            session=vote_session,
            user_id=user_id,
            track=current_track,
            listener_count=listener_count,
            user_in_channel=True,
        )

        # Clear completed vote sessions to avoid state leaking to subsequent tracks.
        if vote_result.action_executed:
            await self._vote_repository.delete(guild_id, VoteType.SKIP)
        else:
            await self._vote_repository.save(vote_session)

        return VoteSkipResult.from_vote_result(
            vote_result,
            votes_current=vote_session.vote_count,
            votes_needed=vote_session.threshold,
        )
