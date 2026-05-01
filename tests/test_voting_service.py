"""Unit tests for VotingApplicationService.vote_skip and VoteSkipResult."""

from unittest.mock import AsyncMock

import pytest

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.domain.voting.entities import VoteSession
from discord_music_player.domain.voting.enums import VoteResult, VoteType


class TestVoteSkipResult:
    def test_from_vote_result_factory(self):
        from discord_music_player.application.services.voting_service import VoteSkipResult

        result = VoteSkipResult.from_vote_result(
            VoteResult.VOTE_RECORDED, votes_current=2, votes_needed=3
        )
        assert result.result == VoteResult.VOTE_RECORDED
        assert result.votes_current == 2
        assert result.votes_needed == 3
        assert result.is_success is True

    def test_is_success_from_vote_result(self):
        from discord_music_player.application.services.voting_service import VoteSkipResult

        success_result = VoteSkipResult.from_vote_result(VoteResult.VOTE_RECORDED)
        assert success_result.is_success is True

        error_result = VoteSkipResult.from_vote_result(VoteResult.NOT_IN_CHANNEL)
        assert error_result.is_success is False


class TestVotingApplicationServiceVoteSkip:
    @pytest.fixture
    def mock_session_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_vote_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session_repo, mock_vote_repo, mock_voice_adapter):
        from discord_music_player.application.services.voting_service import (
            VotingApplicationService,
        )

        return VotingApplicationService(
            session_repository=mock_session_repo,
            vote_repository=mock_vote_repo,
            voice_adapter=mock_voice_adapter,
        )

    @pytest.fixture
    def sample_track(self):
        return Track(
            id=TrackId(value="test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            requested_by_id=111,
        )

    @pytest.mark.asyncio
    async def test_no_session_returns_no_playing(self, service, mock_session_repo):
        mock_session_repo.get.return_value = None

        result = await service.vote_skip(guild_id=123456, user_id=789, user_channel_id=999)

        assert result.result == VoteResult.NO_PLAYING

    @pytest.mark.asyncio
    async def test_no_current_track_returns_no_playing(self, service, mock_session_repo):
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session

        result = await service.vote_skip(guild_id=123456, user_id=789, user_channel_id=999)

        assert result.result == VoteResult.NO_PLAYING

    @pytest.mark.asyncio
    async def test_not_in_voice_channel(self, service, mock_session_repo, sample_track):
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session

        result = await service.vote_skip(guild_id=123456, user_id=789, user_channel_id=None)

        assert result.result == VoteResult.NOT_IN_CHANNEL

    @pytest.mark.asyncio
    async def test_user_not_in_bot_channel(
        self, service, mock_session_repo, mock_voice_adapter, sample_track
    ):
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222]

        result = await service.vote_skip(guild_id=123456, user_id=789, user_channel_id=999)

        assert result.result == VoteResult.NOT_IN_CHANNEL

    @pytest.mark.asyncio
    async def test_requester_auto_skip(
        self, service, mock_session_repo, mock_vote_repo, mock_voice_adapter, sample_track
    ):
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222, 333]

        result = await service.vote_skip(guild_id=123456, user_id=111, user_channel_id=999)

        assert result.result == VoteResult.REQUESTER_SKIP
        mock_vote_repo.delete.assert_awaited_once_with(123456, VoteType.SKIP)

    @pytest.mark.asyncio
    async def test_small_audience_auto_skip(
        self, service, mock_session_repo, mock_vote_repo, mock_voice_adapter, sample_track
    ):
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222]

        result = await service.vote_skip(guild_id=123456, user_id=222, user_channel_id=999)

        assert result.result == VoteResult.AUTO_SKIP
        mock_vote_repo.delete.assert_awaited_once_with(123456, VoteType.SKIP)

    @pytest.mark.asyncio
    async def test_vote_added(
        self, service, mock_session_repo, mock_vote_repo, mock_voice_adapter, sample_track
    ):
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222, 333, 444, 555]

        vote_session = VoteSession(
            guild_id=123456,
            track_id=TrackId(value="test123"),
            vote_type=VoteType.SKIP,
            threshold=3,
        )
        mock_vote_repo.get_or_create.return_value = vote_session

        result = await service.vote_skip(guild_id=123456, user_id=222, user_channel_id=999)

        assert result.result == VoteResult.VOTE_RECORDED
        mock_vote_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_threshold_met_deletes_session(
        self, service, mock_session_repo, mock_vote_repo, mock_voice_adapter, sample_track
    ):
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222, 333]

        vote_session = VoteSession(
            guild_id=123456,
            track_id=TrackId(value="test123"),
            vote_type=VoteType.SKIP,
            threshold=2,
            initial_voters={111},
        )
        mock_vote_repo.get_or_create.return_value = vote_session

        result = await service.vote_skip(guild_id=123456, user_id=222, user_channel_id=999)

        assert result.result == VoteResult.THRESHOLD_MET
        mock_vote_repo.delete.assert_awaited_once_with(123456, VoteType.SKIP)
        mock_vote_repo.save.assert_not_called()
