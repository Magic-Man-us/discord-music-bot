"""
Unit Tests for VoteSkipCommand and VoteSkipHandler.
Uses mocking to isolate from infrastructure dependencies.
"""

from unittest.mock import AsyncMock

import pytest

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.domain.voting.entities import VoteSession
from discord_music_player.domain.voting.enums import VoteResult, VoteType


class TestVoteSkipCommand:
    """Unit tests for VoteSkipCommand."""

    def test_create_valid_command(self):
        """Should create command with valid parameters."""
        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        cmd = VoteSkipCommand(guild_id=123456, user_id=789)
        assert cmd.guild_id == 123456
        assert cmd.user_id == 789
        assert cmd.user_channel_id is None

    def test_with_channel_id(self):
        """Should allow user_channel_id."""
        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        cmd = VoteSkipCommand(guild_id=123456, user_id=789, user_channel_id=999)
        assert cmd.user_channel_id == 999

    def test_invalid_guild_id_raises_error(self):
        """Should raise ValueError for non-positive guild ID."""
        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        with pytest.raises(ValueError):
            VoteSkipCommand(guild_id=0, user_id=789)

    def test_invalid_user_id_raises_error(self):
        """Should raise ValueError for non-positive user ID."""
        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        with pytest.raises(ValueError):
            VoteSkipCommand(guild_id=123456, user_id=0)


class TestVoteSkipResult:
    """Unit tests for VoteSkipResult."""

    def test_from_vote_result_factory(self):
        """Should create result from VoteResult."""
        from discord_music_player.application.commands.vote_skip import VoteSkipResult

        result = VoteSkipResult.from_vote_result(
            VoteResult.VOTE_RECORDED, votes_current=2, votes_needed=3
        )
        assert result.result == VoteResult.VOTE_RECORDED
        assert result.votes_current == 2
        assert result.votes_needed == 3
        assert result.is_success is True

    def test_is_success_from_vote_result(self):
        """is_success should delegate to VoteResult.is_success."""
        from discord_music_player.application.commands.vote_skip import VoteSkipResult

        success_result = VoteSkipResult.from_vote_result(VoteResult.VOTE_RECORDED)
        assert success_result.is_success is True

        error_result = VoteSkipResult.from_vote_result(VoteResult.NOT_IN_CHANNEL)
        assert error_result.is_success is False


class TestVoteSkipHandler:
    """Unit tests for VoteSkipHandler."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_vote_repo(self):
        """Mock vote session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        return AsyncMock()

    @pytest.fixture
    def handler(self, mock_session_repo, mock_vote_repo, mock_voice_adapter):
        """Create handler with mock dependencies."""
        from discord_music_player.application.commands.vote_skip import VoteSkipHandler

        return VoteSkipHandler(
            session_repository=mock_session_repo,
            vote_repository=mock_vote_repo,
            voice_adapter=mock_voice_adapter,
        )

    @pytest.fixture
    def sample_track(self):
        """Sample track for testing."""
        return Track(
            id=TrackId(value="test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            requested_by_id=111,
        )

    @pytest.mark.asyncio
    async def test_handle_no_session_returns_no_playing(self, handler, mock_session_repo):
        """Should return NO_PLAYING when no session exists."""
        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        mock_session_repo.get.return_value = None
        command = VoteSkipCommand(guild_id=123456, user_id=789)

        result = await handler.handle(command)

        assert result.result == VoteResult.NO_PLAYING

    @pytest.mark.asyncio
    async def test_handle_no_current_track_returns_no_playing(self, handler, mock_session_repo):
        """Should return NO_PLAYING when no current track."""
        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session
        command = VoteSkipCommand(guild_id=123456, user_id=789)

        result = await handler.handle(command)

        assert result.result == VoteResult.NO_PLAYING

    @pytest.mark.asyncio
    async def test_handle_not_in_voice_channel(self, handler, mock_session_repo, sample_track):
        """Should return NOT_IN_CHANNEL when user has no channel_id."""
        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session

        command = VoteSkipCommand(
            guild_id=123456,
            user_id=789,
            user_channel_id=None,  # Not in channel
        )

        result = await handler.handle(command)

        assert result.result == VoteResult.NOT_IN_CHANNEL

    @pytest.mark.asyncio
    async def test_handle_user_not_in_bot_channel(
        self, handler, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should return NOT_IN_CHANNEL when user not in bot's channel."""
        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222]  # User 789 not here

        command = VoteSkipCommand(
            guild_id=123456,
            user_id=789,
            user_channel_id=999,
        )

        result = await handler.handle(command)

        assert result.result == VoteResult.NOT_IN_CHANNEL

    @pytest.mark.asyncio
    async def test_handle_requester_auto_skip(
        self, handler, mock_session_repo, mock_vote_repo, mock_voice_adapter, sample_track
    ):
        """Should return REQUESTER_SKIP when requester votes to skip."""
        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track  # Requested by user 111
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222, 333]

        command = VoteSkipCommand(
            guild_id=123456,
            user_id=111,  # Same as requester
            user_channel_id=999,
        )

        result = await handler.handle(command)

        assert result.result == VoteResult.REQUESTER_SKIP
        mock_vote_repo.delete.assert_awaited_once_with(123456, VoteType.SKIP)

    @pytest.mark.asyncio
    async def test_handle_small_audience_auto_skip(
        self, handler, mock_session_repo, mock_vote_repo, mock_voice_adapter, sample_track
    ):
        """Should return AUTO_SKIP with small audience."""
        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222]  # 2 listeners

        command = VoteSkipCommand(
            guild_id=123456,
            user_id=222,
            user_channel_id=999,
        )

        result = await handler.handle(command)

        assert result.result == VoteResult.AUTO_SKIP
        mock_vote_repo.delete.assert_awaited_once_with(123456, VoteType.SKIP)

    @pytest.mark.asyncio
    async def test_handle_vote_added(
        self, handler, mock_session_repo, mock_vote_repo, mock_voice_adapter, sample_track
    ):
        """Should add vote and return ADDED."""
        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222, 333, 444, 555]

        # Create vote session
        vote_session = VoteSession(
            guild_id=123456,
            track_id=TrackId(value="test123"),
            vote_type=VoteType.SKIP,
            threshold=3,
        )
        mock_vote_repo.get_or_create.return_value = vote_session

        command = VoteSkipCommand(
            guild_id=123456,
            user_id=222,
            user_channel_id=999,
        )

        result = await handler.handle(command)

        assert result.result == VoteResult.VOTE_RECORDED
        mock_vote_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_threshold_met_deletes_session(
        self, handler, mock_session_repo, mock_vote_repo, mock_voice_adapter, sample_track
    ):
        """Should delete the vote session when threshold is met."""
        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222, 333]  # threshold=2

        vote_session = VoteSession(
            guild_id=123456,
            track_id=TrackId(value="test123"),
            vote_type=VoteType.SKIP,
            threshold=2,
            initial_voters={111},
        )
        mock_vote_repo.get_or_create.return_value = vote_session

        command = VoteSkipCommand(
            guild_id=123456,
            user_id=222,
            user_channel_id=999,
        )

        result = await handler.handle(command)

        assert result.result == VoteResult.THRESHOLD_MET
        mock_vote_repo.delete.assert_awaited_once_with(123456, VoteType.SKIP)
        mock_vote_repo.save.assert_not_called()
