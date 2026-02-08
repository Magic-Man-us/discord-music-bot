"""
Unit Tests for Application Layer Commands

Tests for:
- ClearQueueCommand, ClearQueueHandler
- PlayTrackCommand, PlayTrackHandler
- SkipTrackCommand, SkipTrackHandler
- StopPlaybackCommand, StopPlaybackHandler
- VoteSkipCommand, VoteSkipHandler

Uses mocking to isolate from infrastructure dependencies.
"""

from unittest.mock import AsyncMock

import pytest

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.value_objects import PlaybackState, TrackId
from discord_music_player.domain.voting.entities import VoteSession
from discord_music_player.domain.voting.value_objects import VoteResult, VoteType

# =============================================================================
# ClearQueue Command Tests
# =============================================================================


class TestClearQueueCommand:
    """Unit tests for ClearQueueCommand."""

    def test_create_valid_command(self):
        """Should create command with valid parameters."""
        from discord_music_player.application.commands.clear_queue import ClearQueueCommand

        cmd = ClearQueueCommand(guild_id=123456, user_id=789)
        assert cmd.guild_id == 123456
        assert cmd.user_id == 789

    def test_invalid_guild_id_raises_error(self):
        """Should raise ValueError for non-positive guild ID."""
        from discord_music_player.application.commands.clear_queue import ClearQueueCommand

        with pytest.raises(ValueError, match="Guild ID must be positive"):
            ClearQueueCommand(guild_id=0, user_id=789)

        with pytest.raises(ValueError, match="Guild ID must be positive"):
            ClearQueueCommand(guild_id=-1, user_id=789)

    def test_invalid_user_id_raises_error(self):
        """Should raise ValueError for non-positive user ID."""
        from discord_music_player.application.commands.clear_queue import ClearQueueCommand

        with pytest.raises(ValueError, match="User ID must be positive"):
            ClearQueueCommand(guild_id=123456, user_id=0)

        with pytest.raises(ValueError, match="User ID must be positive"):
            ClearQueueCommand(guild_id=123456, user_id=-1)


class TestClearStatus:
    """Unit tests for ClearStatus enum."""

    def test_status_values(self):
        """Should have expected status values."""
        from discord_music_player.application.commands.clear_queue import ClearStatus

        assert ClearStatus.SUCCESS.value == "success"
        assert ClearStatus.QUEUE_EMPTY.value == "queue_empty"
        assert ClearStatus.NOT_IN_CHANNEL.value == "not_in_channel"
        assert ClearStatus.ERROR.value == "error"


class TestClearResult:
    """Unit tests for ClearResult."""

    def test_success_factory(self):
        """Should create success result with tracks_cleared."""
        from discord_music_player.application.commands.clear_queue import ClearResult, ClearStatus

        result = ClearResult.success(tracks_cleared=5)
        assert result.status == ClearStatus.SUCCESS
        assert result.tracks_cleared == 5
        assert result.is_success is True
        assert "5 tracks" in result.message

    def test_error_factory(self):
        """Should create error result with status and message."""
        from discord_music_player.application.commands.clear_queue import ClearResult, ClearStatus

        result = ClearResult.error(ClearStatus.QUEUE_EMPTY, "Queue is empty")
        assert result.status == ClearStatus.QUEUE_EMPTY
        assert result.message == "Queue is empty"
        assert result.is_success is False
        assert result.tracks_cleared == 0

    def test_is_success_property(self):
        """is_success should only be True for SUCCESS status."""
        from discord_music_player.application.commands.clear_queue import ClearResult, ClearStatus

        success_result = ClearResult(status=ClearStatus.SUCCESS, message="OK")
        error_result = ClearResult(status=ClearStatus.ERROR, message="Failed")

        assert success_result.is_success is True
        assert error_result.is_success is False


class TestClearQueueHandler:
    """Unit tests for ClearQueueHandler."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def handler(self, mock_session_repo):
        """Create handler with mock dependencies."""
        from discord_music_player.application.commands.clear_queue import ClearQueueHandler

        return ClearQueueHandler(session_repository=mock_session_repo)

    @pytest.fixture
    def sample_track(self):
        """Sample track for testing."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
        )

    @pytest.mark.asyncio
    async def test_handle_no_session_returns_queue_empty(self, handler, mock_session_repo):
        """Should return QUEUE_EMPTY when no session exists."""
        from discord_music_player.application.commands.clear_queue import (
            ClearQueueCommand,
            ClearStatus,
        )

        mock_session_repo.get.return_value = None
        command = ClearQueueCommand(guild_id=123456, user_id=789)

        result = await handler.handle(command)

        assert result.status == ClearStatus.QUEUE_EMPTY
        assert result.is_success is False

    @pytest.mark.asyncio
    async def test_handle_empty_queue_returns_queue_empty(self, handler, mock_session_repo):
        """Should return QUEUE_EMPTY when queue is empty."""
        from discord_music_player.application.commands.clear_queue import (
            ClearQueueCommand,
            ClearStatus,
        )

        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session
        command = ClearQueueCommand(guild_id=123456, user_id=789)

        result = await handler.handle(command)

        assert result.status == ClearStatus.QUEUE_EMPTY

    @pytest.mark.asyncio
    async def test_handle_clears_queue_successfully(self, handler, mock_session_repo, sample_track):
        """Should clear queue and return success."""
        from discord_music_player.application.commands.clear_queue import (
            ClearQueueCommand,
            ClearStatus,
        )

        session = GuildPlaybackSession(guild_id=123456)
        session.enqueue(sample_track)
        mock_session_repo.get.return_value = session
        command = ClearQueueCommand(guild_id=123456, user_id=789)

        result = await handler.handle(command)

        assert result.status == ClearStatus.SUCCESS
        assert result.tracks_cleared == 1
        mock_session_repo.save.assert_called_once_with(session)


# =============================================================================
# PlayTrack Command Tests
# =============================================================================


class TestPlayTrackCommand:
    """Unit tests for PlayTrackCommand."""

    def test_create_valid_command(self):
        """Should create command with valid parameters."""
        from discord_music_player.application.commands.play_track import PlayTrackCommand

        cmd = PlayTrackCommand(
            guild_id=123456,
            channel_id=789,
            user_id=111,
            user_name="TestUser",
            query="never gonna give you up",
        )
        assert cmd.guild_id == 123456
        assert cmd.channel_id == 789
        assert cmd.user_id == 111
        assert cmd.user_name == "TestUser"
        assert cmd.query == "never gonna give you up"
        assert cmd.play_next is False
        assert cmd.want_recommendations is False
        assert cmd.start_playing is True

    def test_play_next_option(self):
        """Should allow play_next flag."""
        from discord_music_player.application.commands.play_track import PlayTrackCommand

        cmd = PlayTrackCommand(
            guild_id=123456,
            channel_id=789,
            user_id=111,
            user_name="TestUser",
            query="test query",
            play_next=True,
        )
        assert cmd.play_next is True

    def test_invalid_guild_id_raises_error(self):
        """Should raise ValueError for non-positive guild ID."""
        from pydantic import ValidationError

        from discord_music_player.application.commands.play_track import PlayTrackCommand

        with pytest.raises(ValidationError, match="Discord snowflake ID must be positive"):
            PlayTrackCommand(
                guild_id=0,
                channel_id=789,
                user_id=111,
                user_name="Test",
                query="test",
            )

    def test_invalid_channel_id_raises_error(self):
        """Should raise ValueError for non-positive channel ID."""
        from pydantic import ValidationError

        from discord_music_player.application.commands.play_track import PlayTrackCommand

        with pytest.raises(ValidationError, match="Discord snowflake ID must be positive"):
            PlayTrackCommand(
                guild_id=123456,
                channel_id=0,
                user_id=111,
                user_name="Test",
                query="test",
            )

    def test_invalid_user_id_raises_error(self):
        """Should raise ValueError for non-positive user ID."""
        from pydantic import ValidationError

        from discord_music_player.application.commands.play_track import PlayTrackCommand

        with pytest.raises(ValidationError, match="Discord snowflake ID must be positive"):
            PlayTrackCommand(
                guild_id=123456,
                channel_id=789,
                user_id=0,
                user_name="Test",
                query="test",
            )

    def test_empty_query_raises_error(self):
        """Should raise ValueError for empty query."""
        from pydantic import ValidationError

        from discord_music_player.application.commands.play_track import PlayTrackCommand

        with pytest.raises(ValidationError, match="Query cannot be empty"):
            PlayTrackCommand(
                guild_id=123456,
                channel_id=789,
                user_id=111,
                user_name="Test",
                query="",
            )

        with pytest.raises(ValueError, match="Query cannot be empty"):
            PlayTrackCommand(
                guild_id=123456,
                channel_id=789,
                user_id=111,
                user_name="Test",
                query="   ",
            )


class TestPlayTrackStatus:
    """Unit tests for PlayTrackStatus enum."""

    def test_status_values(self):
        """Should have expected status values."""
        from discord_music_player.application.commands.play_track import PlayTrackStatus

        assert PlayTrackStatus.SUCCESS.value == "success"
        assert PlayTrackStatus.QUEUED.value == "queued"
        assert PlayTrackStatus.NOW_PLAYING.value == "now_playing"
        assert PlayTrackStatus.TRACK_NOT_FOUND.value == "track_not_found"
        assert PlayTrackStatus.RESOLUTION_ERROR.value == "resolution_error"
        assert PlayTrackStatus.VOICE_ERROR.value == "voice_error"
        assert PlayTrackStatus.QUEUE_FULL.value == "queue_full"


class TestPlayTrackResult:
    """Unit tests for PlayTrackResult."""

    @pytest.fixture
    def sample_track(self):
        """Sample track for testing."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
        )

    def test_success_factory_queued(self, sample_track):
        """Should create queued result when not started playing."""
        from discord_music_player.application.commands.play_track import (
            PlayTrackResult,
            PlayTrackStatus,
        )

        result = PlayTrackResult.success(
            track=sample_track,
            queue_position=2,
            queue_length=3,
            started_playing=False,
        )
        assert result.status == PlayTrackStatus.QUEUED
        assert result.is_success is True
        assert result.track == sample_track
        assert result.queue_position == 2
        assert "position 3" in result.message  # 1-indexed for display

    def test_success_factory_now_playing(self, sample_track):
        """Should create now_playing result when started playing."""
        from discord_music_player.application.commands.play_track import (
            PlayTrackResult,
            PlayTrackStatus,
        )

        result = PlayTrackResult.success(
            track=sample_track,
            queue_position=0,
            queue_length=1,
            started_playing=True,
        )
        assert result.status == PlayTrackStatus.NOW_PLAYING
        assert result.is_success is True
        assert result.started_playing is True
        assert "Now playing" in result.message

    def test_error_factory(self):
        """Should create error result."""
        from discord_music_player.application.commands.play_track import (
            PlayTrackResult,
            PlayTrackStatus,
        )

        result = PlayTrackResult.error(PlayTrackStatus.VOICE_ERROR, "Could not connect")
        assert result.status == PlayTrackStatus.VOICE_ERROR
        assert result.is_success is False
        assert result.message == "Could not connect"
        assert result.track is None

    def test_is_success_for_various_statuses(self, sample_track):
        """is_success should be True for success statuses."""
        from discord_music_player.application.commands.play_track import (
            PlayTrackResult,
            PlayTrackStatus,
        )

        success_statuses = [
            PlayTrackStatus.SUCCESS,
            PlayTrackStatus.QUEUED,
            PlayTrackStatus.NOW_PLAYING,
        ]
        for status in success_statuses:
            result = PlayTrackResult(status=status, message="OK", track=sample_track)
            assert result.is_success is True

        error_statuses = [
            PlayTrackStatus.VOICE_ERROR,
            PlayTrackStatus.TRACK_NOT_FOUND,
            PlayTrackStatus.RESOLUTION_ERROR,
        ]
        for status in error_statuses:
            result = PlayTrackResult(status=status, message="Error")
            assert result.is_success is False


class TestPlayTrackHandler:
    """Unit tests for PlayTrackHandler."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        return AsyncMock()

    @pytest.fixture
    def handler(self, mock_session_repo, mock_audio_resolver, mock_voice_adapter):
        """Create handler with mock dependencies."""
        from discord_music_player.application.commands.play_track import PlayTrackHandler

        return PlayTrackHandler(
            session_repository=mock_session_repo,
            audio_resolver=mock_audio_resolver,
            voice_adapter=mock_voice_adapter,
        )

    @pytest.fixture
    def sample_track(self):
        """Sample track for testing."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            duration_seconds=180,
        )

    @pytest.fixture
    def valid_command(self):
        """Valid play track command."""
        from discord_music_player.application.commands.play_track import PlayTrackCommand

        return PlayTrackCommand(
            guild_id=123456,
            channel_id=789,
            user_id=111,
            user_name="TestUser",
            query="test query",
        )

    @pytest.mark.asyncio
    async def test_handle_voice_connection_fails(self, handler, mock_voice_adapter, valid_command):
        """Should return VOICE_ERROR when cannot connect to voice."""
        from discord_music_player.application.commands.play_track import PlayTrackStatus

        mock_voice_adapter.ensure_connected.return_value = False

        result = await handler.handle(valid_command)

        assert result.status == PlayTrackStatus.VOICE_ERROR
        assert result.is_success is False

    @pytest.mark.asyncio
    async def test_handle_track_not_found(
        self, handler, mock_voice_adapter, mock_audio_resolver, valid_command
    ):
        """Should return TRACK_NOT_FOUND when resolver returns None."""
        from discord_music_player.application.commands.play_track import PlayTrackStatus

        mock_voice_adapter.ensure_connected.return_value = True
        mock_audio_resolver.resolve.return_value = None

        result = await handler.handle(valid_command)

        assert result.status == PlayTrackStatus.TRACK_NOT_FOUND

    @pytest.mark.asyncio
    async def test_handle_resolution_error(
        self, handler, mock_voice_adapter, mock_audio_resolver, valid_command
    ):
        """Should return RESOLUTION_ERROR on resolver exception."""
        from discord_music_player.application.commands.play_track import PlayTrackStatus

        mock_voice_adapter.ensure_connected.return_value = True
        mock_audio_resolver.resolve.side_effect = Exception("Network error")

        result = await handler.handle(valid_command)

        assert result.status == PlayTrackStatus.RESOLUTION_ERROR
        assert "Network error" in result.message

    @pytest.mark.asyncio
    async def test_handle_queue_full(
        self,
        handler,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_session_repo,
        sample_track,
        valid_command,
    ):
        """Should return QUEUE_FULL when queue is at capacity."""
        from discord_music_player.application.commands.play_track import PlayTrackStatus

        mock_voice_adapter.ensure_connected.return_value = True
        mock_audio_resolver.resolve.return_value = sample_track

        # Create session with full queue
        session = GuildPlaybackSession(guild_id=123456)
        for i in range(GuildPlaybackSession.MAX_QUEUE_SIZE):
            track = Track(
                id=TrackId(f"track{i}"),
                title=f"Track {i}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
            )
            session.queue.append(track)
        mock_session_repo.get_or_create.return_value = session

        result = await handler.handle(valid_command)

        assert result.status == PlayTrackStatus.QUEUE_FULL

    @pytest.mark.asyncio
    async def test_handle_enqueue_success(
        self,
        handler,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_session_repo,
        sample_track,
        valid_command,
    ):
        """Should successfully enqueue track."""

        mock_voice_adapter.ensure_connected.return_value = True
        mock_audio_resolver.resolve.return_value = sample_track

        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get_or_create.return_value = session

        result = await handler.handle(valid_command)

        assert result.is_success is True
        assert result.track.title == sample_track.title
        assert result.track.requested_by_id == valid_command.user_id
        mock_session_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_play_next_enqueues_at_front(
        self,
        handler,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_session_repo,
        sample_track,
    ):
        """Should enqueue track at front when play_next is True."""
        from discord_music_player.application.commands.play_track import PlayTrackCommand

        mock_voice_adapter.ensure_connected.return_value = True
        mock_audio_resolver.resolve.return_value = sample_track

        # Session with existing track in queue
        session = GuildPlaybackSession(guild_id=123456)
        existing_track = Track(
            id=TrackId("existing"),
            title="Existing Track",
            webpage_url="https://youtube.com/watch?v=existing",
        )
        session.enqueue(existing_track)
        mock_session_repo.get_or_create.return_value = session

        command = PlayTrackCommand(
            guild_id=123456,
            channel_id=789,
            user_id=111,
            user_name="TestUser",
            query="test",
            play_next=True,
        )

        result = await handler.handle(command)

        assert result.is_success is True
        assert result.queue_position == 0  # At front


# =============================================================================
# SkipTrack Command Tests
# =============================================================================


class TestSkipTrackCommand:
    """Unit tests for SkipTrackCommand."""

    def test_create_valid_command(self):
        """Should create command with valid parameters."""
        from discord_music_player.application.commands.skip_track import SkipTrackCommand

        cmd = SkipTrackCommand(guild_id=123456, user_id=789)
        assert cmd.guild_id == 123456
        assert cmd.user_id == 789
        assert cmd.user_channel_id is None
        assert cmd.force is False

    def test_force_skip_option(self):
        """Should allow force skip flag."""
        from discord_music_player.application.commands.skip_track import SkipTrackCommand

        cmd = SkipTrackCommand(guild_id=123456, user_id=789, force=True)
        assert cmd.force is True

    def test_invalid_guild_id_raises_error(self):
        """Should raise ValueError for non-positive guild ID."""
        from discord_music_player.application.commands.skip_track import SkipTrackCommand

        with pytest.raises(ValueError, match="Guild ID must be positive"):
            SkipTrackCommand(guild_id=0, user_id=789)

    def test_invalid_user_id_raises_error(self):
        """Should raise ValueError for non-positive user ID."""
        from discord_music_player.application.commands.skip_track import SkipTrackCommand

        with pytest.raises(ValueError, match="User ID must be positive"):
            SkipTrackCommand(guild_id=123456, user_id=0)


class TestSkipStatus:
    """Unit tests for SkipStatus enum."""

    def test_status_values(self):
        """Should have expected status values."""
        from discord_music_player.application.commands.skip_track import SkipStatus

        assert SkipStatus.SUCCESS.value == "success"
        assert SkipStatus.NOTHING_PLAYING.value == "nothing_playing"
        assert SkipStatus.NOT_IN_CHANNEL.value == "not_in_channel"
        assert SkipStatus.PERMISSION_DENIED.value == "permission_denied"


class TestSkipResult:
    """Unit tests for SkipResult."""

    @pytest.fixture
    def sample_track(self):
        """Sample track for testing."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
        )

    @pytest.fixture
    def next_track(self):
        """Next track for testing."""
        return Track(
            id=TrackId("next456"),
            title="Next Track",
            webpage_url="https://youtube.com/watch?v=next456",
        )

    def test_success_factory_with_next_track(self, sample_track, next_track):
        """Should create success result with next track info."""
        from discord_music_player.application.commands.skip_track import SkipResult, SkipStatus

        result = SkipResult.success(sample_track, next_track)
        assert result.status == SkipStatus.SUCCESS
        assert result.is_success is True
        assert result.skipped_track == sample_track
        assert result.next_track == next_track
        assert "Now playing" in result.message

    def test_success_factory_queue_empty(self, sample_track):
        """Should create success result indicating empty queue."""
        from discord_music_player.application.commands.skip_track import SkipResult, SkipStatus

        result = SkipResult.success(sample_track, None)
        assert result.status == SkipStatus.SUCCESS
        assert result.next_track is None
        assert "empty" in result.message.lower()

    def test_requires_voting_factory(self):
        """Should create result requiring voting."""
        from discord_music_player.application.commands.skip_track import SkipResult, SkipStatus

        result = SkipResult.requires_voting()
        assert result.status == SkipStatus.PERMISSION_DENIED
        assert result.requires_vote is True
        assert result.is_success is False

    def test_error_factory(self):
        """Should create error result."""
        from discord_music_player.application.commands.skip_track import SkipResult, SkipStatus

        result = SkipResult.error(SkipStatus.NOT_IN_CHANNEL, "Not in channel")
        assert result.status == SkipStatus.NOT_IN_CHANNEL
        assert result.message == "Not in channel"


class TestSkipTrackHandler:
    """Unit tests for SkipTrackHandler."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        return AsyncMock()

    @pytest.fixture
    def handler(self, mock_session_repo, mock_voice_adapter):
        """Create handler with mock dependencies."""
        from discord_music_player.application.commands.skip_track import SkipTrackHandler

        return SkipTrackHandler(
            session_repository=mock_session_repo,
            voice_adapter=mock_voice_adapter,
        )

    @pytest.fixture
    def sample_track(self):
        """Sample track for testing."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            requested_by_id=111,
        )

    @pytest.mark.asyncio
    async def test_handle_no_session_returns_nothing_playing(self, handler, mock_session_repo):
        """Should return NOTHING_PLAYING when no session exists."""
        from discord_music_player.application.commands.skip_track import (
            SkipStatus,
            SkipTrackCommand,
        )

        mock_session_repo.get.return_value = None
        command = SkipTrackCommand(guild_id=123456, user_id=789)

        result = await handler.handle(command)

        assert result.status == SkipStatus.NOTHING_PLAYING

    @pytest.mark.asyncio
    async def test_handle_no_current_track_returns_nothing_playing(
        self, handler, mock_session_repo
    ):
        """Should return NOTHING_PLAYING when no current track."""
        from discord_music_player.application.commands.skip_track import (
            SkipStatus,
            SkipTrackCommand,
        )

        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session
        command = SkipTrackCommand(guild_id=123456, user_id=789)

        result = await handler.handle(command)

        assert result.status == SkipStatus.NOTHING_PLAYING

    @pytest.mark.asyncio
    async def test_handle_not_in_channel_without_force(
        self, handler, mock_session_repo, sample_track
    ):
        """Should return NOT_IN_CHANNEL when user not in voice."""
        from discord_music_player.application.commands.skip_track import (
            SkipStatus,
            SkipTrackCommand,
        )

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session

        command = SkipTrackCommand(
            guild_id=123456,
            user_id=789,
            user_channel_id=None,  # Not in channel
            force=False,
        )

        result = await handler.handle(command)

        assert result.status == SkipStatus.NOT_IN_CHANNEL

    @pytest.mark.asyncio
    async def test_handle_requires_voting_with_many_listeners(
        self, handler, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should require voting when many listeners and user didn't request track."""
        from discord_music_player.application.commands.skip_track import (
            SkipStatus,
            SkipTrackCommand,
        )

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track  # Requested by user 111
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222, 333, 444]  # 4 listeners

        command = SkipTrackCommand(
            guild_id=123456,
            user_id=222,  # Different user
            user_channel_id=999,
            force=False,
        )

        result = await handler.handle(command)

        assert result.status == SkipStatus.PERMISSION_DENIED
        assert result.requires_vote is True

    @pytest.mark.asyncio
    async def test_handle_requester_can_skip_own_track(
        self, handler, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should allow requester to skip their own track."""
        from discord_music_player.application.commands.skip_track import (
            SkipStatus,
            SkipTrackCommand,
        )

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track  # Requested by user 111
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222, 333, 444]

        command = SkipTrackCommand(
            guild_id=123456,
            user_id=111,  # Same as requester
            user_channel_id=999,
            force=False,
        )

        result = await handler.handle(command)

        assert result.status == SkipStatus.SUCCESS
        mock_voice_adapter.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_force_skip_bypasses_voting(
        self, handler, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should skip without voting when force is True."""
        from discord_music_player.application.commands.skip_track import (
            SkipStatus,
            SkipTrackCommand,
        )

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session

        command = SkipTrackCommand(
            guild_id=123456,
            user_id=999,  # Different user
            force=True,
        )

        result = await handler.handle(command)

        assert result.status == SkipStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_handle_small_audience_allows_skip(
        self, handler, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should allow skip with 2 or fewer listeners."""
        from discord_music_player.application.commands.skip_track import (
            SkipStatus,
            SkipTrackCommand,
        )

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session
        mock_voice_adapter.get_listeners.return_value = [111, 222]  # 2 listeners

        command = SkipTrackCommand(
            guild_id=123456,
            user_id=222,
            user_channel_id=999,
            force=False,
        )

        result = await handler.handle(command)

        assert result.status == SkipStatus.SUCCESS


# =============================================================================
# StopPlayback Command Tests
# =============================================================================


class TestStopPlaybackCommand:
    """Unit tests for StopPlaybackCommand."""

    def test_create_valid_command(self):
        """Should create command with valid parameters."""
        from discord_music_player.application.commands.stop_playback import StopPlaybackCommand

        cmd = StopPlaybackCommand(guild_id=123456, user_id=789)
        assert cmd.guild_id == 123456
        assert cmd.user_id == 789
        assert cmd.clear_queue is True  # Default
        assert cmd.disconnect is False  # Default

    def test_options(self):
        """Should allow options."""
        from discord_music_player.application.commands.stop_playback import StopPlaybackCommand

        cmd = StopPlaybackCommand(
            guild_id=123456,
            user_id=789,
            clear_queue=False,
            disconnect=True,
        )
        assert cmd.clear_queue is False
        assert cmd.disconnect is True

    def test_invalid_guild_id_raises_error(self):
        """Should raise ValueError for non-positive guild ID."""
        from discord_music_player.application.commands.stop_playback import StopPlaybackCommand

        with pytest.raises(ValueError, match="Guild ID must be positive"):
            StopPlaybackCommand(guild_id=0, user_id=789)

    def test_invalid_user_id_raises_error(self):
        """Should raise ValueError for non-positive user ID."""
        from discord_music_player.application.commands.stop_playback import StopPlaybackCommand

        with pytest.raises(ValueError, match="User ID must be positive"):
            StopPlaybackCommand(guild_id=123456, user_id=0)


class TestStopStatus:
    """Unit tests for StopStatus enum."""

    def test_status_values(self):
        """Should have expected status values."""
        from discord_music_player.application.commands.stop_playback import StopStatus

        assert StopStatus.SUCCESS.value == "success"
        assert StopStatus.NOTHING_PLAYING.value == "nothing_playing"
        assert StopStatus.NOT_IN_CHANNEL.value == "not_in_channel"
        assert StopStatus.ERROR.value == "error"


class TestStopResult:
    """Unit tests for StopResult."""

    def test_success_factory_basic(self):
        """Should create basic success result."""
        from discord_music_player.application.commands.stop_playback import StopResult, StopStatus

        result = StopResult.success()
        assert result.status == StopStatus.SUCCESS
        assert result.is_success is True
        assert "Stopped" in result.message

    def test_success_factory_with_tracks_cleared(self):
        """Should create success result with tracks cleared count."""
        from discord_music_player.application.commands.stop_playback import StopResult

        result = StopResult.success(tracks_cleared=5)
        assert result.tracks_cleared == 5
        assert "5 tracks" in result.message

    def test_success_factory_with_disconnect(self):
        """Should create success result indicating disconnect."""
        from discord_music_player.application.commands.stop_playback import StopResult

        result = StopResult.success(disconnected=True)
        assert result.disconnected is True
        assert "disconnected" in result.message.lower()

    def test_error_factory(self):
        """Should create error result."""
        from discord_music_player.application.commands.stop_playback import StopResult, StopStatus

        result = StopResult.error(StopStatus.ERROR, "Something went wrong")
        assert result.status == StopStatus.ERROR
        assert result.message == "Something went wrong"
        assert result.is_success is False


class TestStopPlaybackHandler:
    """Unit tests for StopPlaybackHandler."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        return AsyncMock()

    @pytest.fixture
    def handler(self, mock_session_repo, mock_voice_adapter):
        """Create handler with mock dependencies."""
        from discord_music_player.application.commands.stop_playback import StopPlaybackHandler

        return StopPlaybackHandler(
            session_repository=mock_session_repo,
            voice_adapter=mock_voice_adapter,
        )

    @pytest.fixture
    def sample_track(self):
        """Sample track for testing."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
        )

    @pytest.mark.asyncio
    async def test_handle_no_session_returns_nothing_playing(self, handler, mock_session_repo):
        """Should return NOTHING_PLAYING when no session exists."""
        from discord_music_player.application.commands.stop_playback import (
            StopPlaybackCommand,
            StopStatus,
        )

        mock_session_repo.get.return_value = None
        command = StopPlaybackCommand(guild_id=123456, user_id=789)

        result = await handler.handle(command)

        assert result.status == StopStatus.NOTHING_PLAYING

    @pytest.mark.asyncio
    async def test_handle_stops_playback(self, handler, mock_session_repo, mock_voice_adapter):
        """Should stop playback."""
        from discord_music_player.application.commands.stop_playback import (
            StopPlaybackCommand,
            StopStatus,
        )

        session = GuildPlaybackSession(guild_id=123456)
        session.state = PlaybackState.PLAYING
        mock_session_repo.get.return_value = session

        command = StopPlaybackCommand(guild_id=123456, user_id=789, clear_queue=False)

        result = await handler.handle(command)

        assert result.status == StopStatus.SUCCESS
        mock_voice_adapter.stop.assert_called_once()
        mock_session_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_clears_queue(
        self, handler, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should clear queue when clear_queue is True."""
        from discord_music_player.application.commands.stop_playback import StopPlaybackCommand

        session = GuildPlaybackSession(guild_id=123456)
        session.enqueue(sample_track)
        mock_session_repo.get.return_value = session

        command = StopPlaybackCommand(guild_id=123456, user_id=789, clear_queue=True)

        result = await handler.handle(command)

        assert result.tracks_cleared == 1

    @pytest.mark.asyncio
    async def test_handle_disconnects_and_deletes_session(
        self, handler, mock_session_repo, mock_voice_adapter
    ):
        """Should disconnect and delete session when disconnect is True."""
        from discord_music_player.application.commands.stop_playback import StopPlaybackCommand

        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session
        mock_voice_adapter.disconnect.return_value = True

        command = StopPlaybackCommand(
            guild_id=123456,
            user_id=789,
            disconnect=True,
        )

        result = await handler.handle(command)

        assert result.disconnected is True
        mock_voice_adapter.disconnect.assert_called_once_with(123456)
        mock_session_repo.delete.assert_called_once_with(123456)


# =============================================================================
# VoteSkip Command Tests
# =============================================================================


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
        from pydantic import ValidationError

        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        with pytest.raises(ValidationError, match="Discord snowflake ID must be positive"):
            VoteSkipCommand(guild_id=0, user_id=789)

    def test_invalid_user_id_raises_error(self):
        """Should raise ValueError for non-positive user ID."""
        from pydantic import ValidationError

        from discord_music_player.application.commands.vote_skip import VoteSkipCommand

        with pytest.raises(ValidationError, match="Discord snowflake ID must be positive"):
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
            id=TrackId("test123"),
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
            track_id="test123",
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
            track_id="test123",
            vote_type=VoteType.SKIP,
            threshold=2,
        )
        vote_session._voters = {111}
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
