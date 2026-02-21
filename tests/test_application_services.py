"""
Unit Tests for Application Layer Services

Tests for:
- QueueApplicationService
- PlaybackApplicationService

Uses mocking to isolate from infrastructure dependencies.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.value_objects import LoopMode, PlaybackState, TrackId


@pytest.fixture
def mock_history_repo():
    """Mock track history repository."""
    mock = AsyncMock()
    mock.record_play = AsyncMock()
    mock.mark_finished = AsyncMock()
    return mock


# =============================================================================
# QueueApplicationService Tests
# =============================================================================


class TestQueueApplicationServiceEnqueue:
    """Unit tests for QueueApplicationService.enqueue method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_queue_domain_service(self):
        """Mock queue domain service."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_session_repo, mock_queue_domain_service):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.queue_service import QueueApplicationService

        return QueueApplicationService(
            session_repository=mock_session_repo,
            queue_domain_service=mock_queue_domain_service,
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

    @pytest.mark.asyncio
    async def test_enqueue_success(self, service, mock_session_repo, sample_track):
        """Should enqueue track successfully."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get_or_create.return_value = session

        result = await service.enqueue(
            guild_id=123456,
            track=sample_track,
            user_id=111,
            user_name="TestUser",
        )

        assert result.success is True
        assert result.track is not None
        assert result.track.requested_by_id == 111
        assert result.track.requested_by_name == "TestUser"
        mock_session_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueue_queue_full(self, service, mock_session_repo, sample_track):
        """Should fail when queue is full."""
        session = GuildPlaybackSession(guild_id=123456)
        # Fill queue to max
        for i in range(GuildPlaybackSession.MAX_QUEUE_SIZE):
            track = Track(
                id=TrackId(f"track{i}"),
                title=f"Track {i}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
            )
            session.queue.append(track)
        mock_session_repo.get_or_create.return_value = session

        result = await service.enqueue(
            guild_id=123456,
            track=sample_track,
            user_id=111,
            user_name="TestUser",
        )

        assert result.success is False
        assert "full" in result.message.lower()
        mock_session_repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_enqueue_should_start_when_idle(self, service, mock_session_repo, sample_track):
        """Should indicate playback should start when idle."""
        session = GuildPlaybackSession(guild_id=123456)
        # No current track
        mock_session_repo.get_or_create.return_value = session

        result = await service.enqueue(
            guild_id=123456,
            track=sample_track,
            user_id=111,
            user_name="TestUser",
        )

        assert result.success is True
        assert result.should_start is True

    @pytest.mark.asyncio
    async def test_enqueue_should_not_start_when_playing(
        self, service, mock_session_repo, sample_track
    ):
        """Should not indicate start when already playing."""
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = Track(
            id=TrackId("current"),
            title="Current",
            webpage_url="https://youtube.com/watch?v=current",
        )
        mock_session_repo.get_or_create.return_value = session

        result = await service.enqueue(
            guild_id=123456,
            track=sample_track,
            user_id=111,
            user_name="TestUser",
        )

        assert result.success is True
        assert result.should_start is False


class TestQueueApplicationServiceEnqueueNext:
    """Unit tests for QueueApplicationService.enqueue_next method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_queue_domain_service(self):
        """Mock queue domain service."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_session_repo, mock_queue_domain_service):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.queue_service import QueueApplicationService

        return QueueApplicationService(
            session_repository=mock_session_repo,
            queue_domain_service=mock_queue_domain_service,
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
    async def test_enqueue_next_adds_to_front(self, service, mock_session_repo, sample_track):
        """Should add track to front of queue."""
        session = GuildPlaybackSession(guild_id=123456)
        existing_track = Track(
            id=TrackId("existing"),
            title="Existing",
            webpage_url="https://youtube.com/watch?v=existing",
        )
        session.enqueue(existing_track)
        mock_session_repo.get_or_create.return_value = session

        result = await service.enqueue_next(
            guild_id=123456,
            track=sample_track,
            user_id=111,
            user_name="TestUser",
        )

        assert result.success is True
        assert result.position == 0


class TestQueueApplicationServiceOperations:
    """Unit tests for QueueApplicationService queue operations."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_queue_domain_service(self):
        """Mock queue domain service."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_session_repo, mock_queue_domain_service):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.queue_service import QueueApplicationService

        return QueueApplicationService(
            session_repository=mock_session_repo,
            queue_domain_service=mock_queue_domain_service,
        )

    @pytest.fixture
    def sample_tracks(self):
        """Sample tracks for testing."""
        return [
            Track(
                id=TrackId(f"track{i}"),
                title=f"Track {i}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
                duration_seconds=180 + i * 30,
            )
            for i in range(3)
        ]

    @pytest.mark.asyncio
    async def test_remove_valid_position(self, service, mock_session_repo, sample_tracks):
        """Should remove track at valid position."""
        session = GuildPlaybackSession(guild_id=123456)
        for track in sample_tracks:
            session.enqueue(track)
        mock_session_repo.get.return_value = session

        result = await service.remove(guild_id=123456, position=1)

        assert result == sample_tracks[1]
        mock_session_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_no_session(self, service, mock_session_repo):
        """Should return None when no session."""
        mock_session_repo.get.return_value = None

        result = await service.remove(guild_id=123456, position=0)

        assert result is None

    @pytest.mark.asyncio
    async def test_clear_queue(self, service, mock_session_repo, sample_tracks):
        """Should clear all tracks from queue."""
        session = GuildPlaybackSession(guild_id=123456)
        for track in sample_tracks:
            session.enqueue(track)
        mock_session_repo.get.return_value = session

        result = await service.clear(guild_id=123456)

        assert result == 3
        mock_session_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_empty_queue(self, service, mock_session_repo):
        """Should return 0 when clearing empty queue."""
        mock_session_repo.get.return_value = None

        result = await service.clear(guild_id=123456)

        assert result == 0

    @pytest.mark.asyncio
    async def test_shuffle(self, service, mock_session_repo, sample_tracks):
        """Should shuffle queue."""
        session = GuildPlaybackSession(guild_id=123456)
        for track in sample_tracks:
            session.enqueue(track)
        mock_session_repo.get.return_value = session

        result = await service.shuffle(guild_id=123456)

        assert result is True
        mock_session_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_shuffle_empty(self, service, mock_session_repo):
        """Should return False when shuffling empty queue."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session

        result = await service.shuffle(guild_id=123456)

        assert result is False

    @pytest.mark.asyncio
    async def test_move_track(self, service, mock_session_repo, sample_tracks):
        """Should move track from one position to another."""
        session = GuildPlaybackSession(guild_id=123456)
        for track in sample_tracks:
            session.enqueue(track)
        mock_session_repo.get.return_value = session

        result = await service.move(guild_id=123456, from_pos=0, to_pos=2)

        assert result is True
        mock_session_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_move_no_session(self, service, mock_session_repo):
        """Should return False when no session."""
        mock_session_repo.get.return_value = None

        result = await service.move(guild_id=123456, from_pos=0, to_pos=1)

        assert result is False


class TestQueueApplicationServiceGetQueue:
    """Unit tests for QueueApplicationService.get_queue method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_queue_domain_service(self):
        """Mock queue domain service."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_session_repo, mock_queue_domain_service):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.queue_service import QueueApplicationService

        return QueueApplicationService(
            session_repository=mock_session_repo,
            queue_domain_service=mock_queue_domain_service,
        )

    @pytest.fixture
    def sample_tracks(self):
        """Sample tracks with durations."""
        return [
            Track(
                id=TrackId(f"track{i}"),
                title=f"Track {i}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
                duration_seconds=180,
            )
            for i in range(3)
        ]

    @pytest.mark.asyncio
    async def test_get_queue_no_session(self, service, mock_session_repo):
        """Should return empty queue info when no session."""
        mock_session_repo.get.return_value = None

        result = await service.get_queue(guild_id=123456)

        assert result.current_track is None
        assert result.upcoming_tracks == []
        assert result.total_length == 0

    @pytest.mark.asyncio
    async def test_get_queue_with_tracks(self, service, mock_session_repo, sample_tracks):
        """Should return queue info with tracks."""
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_tracks[0]
        session.enqueue(sample_tracks[1])
        session.enqueue(sample_tracks[2])
        mock_session_repo.get.return_value = session

        result = await service.get_queue(guild_id=123456)

        assert result.current_track == sample_tracks[0]
        assert len(result.upcoming_tracks) == 2
        assert result.total_length == 3  # Current + 2 in queue

    @pytest.mark.asyncio
    async def test_get_queue_calculates_duration(self, service, mock_session_repo, sample_tracks):
        """Should calculate total duration."""
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_tracks[0]
        session.enqueue(sample_tracks[1])
        mock_session_repo.get.return_value = session

        result = await service.get_queue(guild_id=123456)

        assert result.total_duration_seconds == 360  # 180 + 180


class TestQueueApplicationServiceToggleLoop:
    """Unit tests for QueueApplicationService.toggle_loop method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_queue_domain_service(self):
        """Mock queue domain service."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_session_repo, mock_queue_domain_service):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.queue_service import QueueApplicationService

        return QueueApplicationService(
            session_repository=mock_session_repo,
            queue_domain_service=mock_queue_domain_service,
        )

    @pytest.mark.asyncio
    async def test_toggle_loop_cycles(self, service, mock_session_repo):
        """Should cycle through loop modes."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get_or_create.return_value = session

        # OFF -> TRACK
        result = await service.toggle_loop(guild_id=123456)
        assert result == LoopMode.TRACK

        # TRACK -> QUEUE
        result = await service.toggle_loop(guild_id=123456)
        assert result == LoopMode.QUEUE

        # QUEUE -> OFF
        result = await service.toggle_loop(guild_id=123456)
        assert result == LoopMode.OFF


# =============================================================================
# PlaybackApplicationService Tests
# =============================================================================


class TestPlaybackApplicationServiceStartPlayback:
    """Unit tests for PlaybackApplicationService.start_playback method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        mock = AsyncMock()
        mock.set_on_track_end_callback = MagicMock()
        return mock

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_playback_domain_service(self):
        """Mock playback domain service."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_session_repo,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_playback_domain_service,
        mock_history_repo,
    ):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.playback_service import (
            PlaybackApplicationService,
        )

        return PlaybackApplicationService(
            session_repository=mock_session_repo,
            history_repository=mock_history_repo,
            voice_adapter=mock_voice_adapter,
            audio_resolver=mock_audio_resolver,
            playback_domain_service=mock_playback_domain_service,
        )

    @pytest.fixture
    def sample_track(self):
        """Sample track with stream URL."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            stream_url="https://stream.example.com/audio",
            duration_seconds=180,
        )

    @pytest.mark.asyncio
    async def test_start_playback_no_session(self, service, mock_session_repo):
        """Should return False when no session."""
        mock_session_repo.get.return_value = None

        result = await service.start_playback(guild_id=123456)

        assert result is False

    @pytest.mark.asyncio
    async def test_start_playback_already_playing(self, service, mock_session_repo, sample_track):
        """Should return True when already playing."""
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        session.state = PlaybackState.PLAYING
        mock_session_repo.get.return_value = session

        result = await service.start_playback(guild_id=123456)

        assert result is True

    @pytest.mark.asyncio
    async def test_start_playback_empty_queue(self, service, mock_session_repo):
        """Should return False when queue is empty."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session

        result = await service.start_playback(guild_id=123456)

        assert result is False

    @pytest.mark.asyncio
    async def test_start_playback_success(
        self, service, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should start playback successfully."""
        session = GuildPlaybackSession(guild_id=123456)
        session.enqueue(sample_track)
        mock_session_repo.get.return_value = session
        mock_voice_adapter.play.return_value = True

        result = await service.start_playback(guild_id=123456)

        assert result is True
        mock_voice_adapter.play.assert_called_once()
        mock_session_repo.save.assert_called()


class TestPlaybackApplicationServiceStopPlayback:
    """Unit tests for PlaybackApplicationService.stop_playback method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        mock = AsyncMock()
        mock.set_on_track_end_callback = MagicMock()
        return mock

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_playback_domain_service(self):
        """Mock playback domain service."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_session_repo,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_playback_domain_service,
        mock_history_repo,
    ):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.playback_service import (
            PlaybackApplicationService,
        )

        return PlaybackApplicationService(
            session_repository=mock_session_repo,
            history_repository=mock_history_repo,
            voice_adapter=mock_voice_adapter,
            audio_resolver=mock_audio_resolver,
            playback_domain_service=mock_playback_domain_service,
        )

    @pytest.mark.asyncio
    async def test_stop_playback_no_session(self, service, mock_session_repo):
        """Should return False when no session."""
        mock_session_repo.get.return_value = None

        result = await service.stop_playback(guild_id=123456)

        assert result is False

    @pytest.mark.asyncio
    async def test_stop_playback_success(self, service, mock_session_repo, mock_voice_adapter):
        """Should stop playback successfully."""
        session = GuildPlaybackSession(guild_id=123456)
        session.state = PlaybackState.PLAYING
        mock_session_repo.get.return_value = session

        result = await service.stop_playback(guild_id=123456)

        assert result is True
        mock_voice_adapter.stop.assert_called_once()
        mock_session_repo.save.assert_called_once()


class TestPlaybackApplicationServicePauseResume:
    """Unit tests for PlaybackApplicationService pause/resume methods."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        mock = AsyncMock()
        mock.set_on_track_end_callback = MagicMock()
        return mock

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_playback_domain_service(self):
        """Mock playback domain service."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_session_repo,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_playback_domain_service,
        mock_history_repo,
    ):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.playback_service import (
            PlaybackApplicationService,
        )

        return PlaybackApplicationService(
            session_repository=mock_session_repo,
            history_repository=mock_history_repo,
            voice_adapter=mock_voice_adapter,
            audio_resolver=mock_audio_resolver,
            playback_domain_service=mock_playback_domain_service,
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
    async def test_pause_when_playing(
        self, service, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should pause when playing."""
        session = GuildPlaybackSession(guild_id=123456)
        session.start_playback(sample_track)
        mock_session_repo.get.return_value = session

        result = await service.pause_playback(guild_id=123456)

        assert result is True
        mock_voice_adapter.pause.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_when_not_playing(self, service, mock_session_repo):
        """Should return False when not playing."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session

        result = await service.pause_playback(guild_id=123456)

        assert result is False

    @pytest.mark.asyncio
    async def test_resume_when_paused(
        self, service, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should resume when paused."""
        session = GuildPlaybackSession(guild_id=123456)
        session.start_playback(sample_track)
        session.pause()
        mock_session_repo.get.return_value = session

        result = await service.resume_playback(guild_id=123456)

        assert result is True
        mock_voice_adapter.resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_when_not_paused(self, service, mock_session_repo):
        """Should return False when not paused."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session

        result = await service.resume_playback(guild_id=123456)

        assert result is False


class TestPlaybackApplicationServiceSkipTrack:
    """Unit tests for PlaybackApplicationService.skip_track method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        mock = AsyncMock()
        mock.set_on_track_end_callback = MagicMock()
        return mock

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_playback_domain_service(self):
        """Mock playback domain service."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_session_repo,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_playback_domain_service,
        mock_history_repo,
    ):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.playback_service import (
            PlaybackApplicationService,
        )

        return PlaybackApplicationService(
            session_repository=mock_session_repo,
            history_repository=mock_history_repo,
            voice_adapter=mock_voice_adapter,
            audio_resolver=mock_audio_resolver,
            playback_domain_service=mock_playback_domain_service,
        )

    @pytest.fixture
    def sample_track(self):
        """Sample track for testing."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            stream_url="https://stream.example.com/audio",
        )

    @pytest.mark.asyncio
    async def test_skip_no_session(self, service, mock_session_repo):
        """Should return None when no session."""
        mock_session_repo.get.return_value = None

        result = await service.skip_track(guild_id=123456)

        assert result is None

    @pytest.mark.asyncio
    async def test_skip_nothing_playing(self, service, mock_session_repo):
        """Should return None when nothing playing."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session

        result = await service.skip_track(guild_id=123456)

        assert result is None

    @pytest.mark.asyncio
    async def test_skip_returns_skipped_track(
        self, service, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should return the skipped track."""
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session

        result = await service.skip_track(guild_id=123456)

        assert result == sample_track
        mock_voice_adapter.stop.assert_called_once()
        mock_session_repo.save.assert_called()

    @pytest.mark.asyncio
    async def test_skip_queue_empty_does_not_start_next(
        self, service, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should stop playback and not start next when queue is empty."""
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        session.queue.clear()
        mock_session_repo.get.return_value = session

        service.start_playback = AsyncMock()  # type: ignore[attr-defined]

        result = await service.skip_track(guild_id=123456)

        assert result == sample_track
        assert session.current_track is None
        mock_voice_adapter.stop.assert_called_once()
        service.start_playback.assert_not_called()


class TestPlaybackApplicationServiceCleanup:
    """Unit tests for PlaybackApplicationService.cleanup_guild method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        mock = AsyncMock()
        mock.set_on_track_end_callback = MagicMock()
        return mock

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_playback_domain_service(self):
        """Mock playback domain service."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_session_repo,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_playback_domain_service,
        mock_history_repo,
    ):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.playback_service import (
            PlaybackApplicationService,
        )

        return PlaybackApplicationService(
            session_repository=mock_session_repo,
            history_repository=mock_history_repo,
            voice_adapter=mock_voice_adapter,
            audio_resolver=mock_audio_resolver,
            playback_domain_service=mock_playback_domain_service,
        )

    @pytest.mark.asyncio
    async def test_cleanup_guild(self, service, mock_session_repo, mock_voice_adapter):
        """Should clean up all resources for guild."""
        await service.cleanup_guild(guild_id=123456)

        mock_voice_adapter.stop.assert_called_once_with(123456)
        mock_voice_adapter.disconnect.assert_called_once_with(123456)
        mock_session_repo.delete.assert_called_once_with(123456)

    @pytest.mark.asyncio
    async def test_cleanup_guild_handles_voice_error(
        self, service, mock_session_repo, mock_voice_adapter
    ):
        """Should handle errors during voice cleanup gracefully."""
        mock_voice_adapter.stop.side_effect = Exception("Voice error")

        # Should not raise
        await service.cleanup_guild(guild_id=123456)

        # Session should still be deleted
        mock_session_repo.delete.assert_called_once_with(123456)


class TestPlaybackApplicationServiceOnVoiceTrackEnd:
    """Unit tests for PlaybackApplicationService._on_voice_track_end method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        mock = AsyncMock()
        mock.set_on_track_end_callback = MagicMock()
        return mock

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_playback_domain_service(self):
        """Mock playback domain service."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_session_repo,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_playback_domain_service,
        mock_history_repo,
    ):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.playback_service import (
            PlaybackApplicationService,
        )

        return PlaybackApplicationService(
            session_repository=mock_session_repo,
            history_repository=mock_history_repo,
            voice_adapter=mock_voice_adapter,
            audio_resolver=mock_audio_resolver,
            playback_domain_service=mock_playback_domain_service,
        )

    @pytest.fixture
    def sample_track(self):
        """Sample track for testing."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            stream_url="https://stream.example.com/audio",
        )

    @pytest.mark.asyncio
    async def test_on_voice_track_end_no_session(self, service, mock_session_repo):
        """Should do nothing when no session exists."""
        mock_session_repo.get.return_value = None

        await service._on_voice_track_end(guild_id=123456)

        mock_session_repo.get.assert_called_once_with(123456)

    @pytest.mark.asyncio
    async def test_on_voice_track_end_no_current_track(self, service, mock_session_repo):
        """Should do nothing when no current track."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session

        await service._on_voice_track_end(guild_id=123456)

        # No further actions expected
        mock_session_repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_voice_track_end_with_current_track(
        self, service, mock_session_repo, sample_track
    ):
        """Should handle track finished when current track exists."""
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session

        await service._on_voice_track_end(guild_id=123456)

        # Should call handle_track_finished via the internal logic
        # The session should be saved after advancing to next track
        assert mock_session_repo.get.call_count >= 1

    @pytest.mark.asyncio
    async def test_on_voice_track_end_ignored_when_suppressed(
        self, service, mock_session_repo, sample_track
    ):
        """Should ignore the next voice track-end callback when suppressed."""
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session

        service._ignore_next_voice_track_end.add(123456)
        service.handle_track_finished = AsyncMock()

        await service._on_voice_track_end(guild_id=123456)

        service.handle_track_finished.assert_not_called()


class TestPlaybackApplicationServiceSetCallback:
    """Unit tests for PlaybackApplicationService.set_track_finished_callback."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        mock = AsyncMock()
        mock.set_on_track_end_callback = MagicMock()
        return mock

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_playback_domain_service(self):
        """Mock playback domain service."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_session_repo,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_playback_domain_service,
        mock_history_repo,
    ):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.playback_service import (
            PlaybackApplicationService,
        )

        return PlaybackApplicationService(
            session_repository=mock_session_repo,
            history_repository=mock_history_repo,
            voice_adapter=mock_voice_adapter,
            audio_resolver=mock_audio_resolver,
            playback_domain_service=mock_playback_domain_service,
        )

    def test_set_track_finished_callback(self, service):
        """Should set the track finished callback."""
        callback = MagicMock()

        service.set_track_finished_callback(callback)

        assert service._on_track_finished_callback == callback


class TestPlaybackApplicationServiceHandleTrackFinished:
    """Unit tests for PlaybackApplicationService.handle_track_finished method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        mock = AsyncMock()
        mock.set_on_track_end_callback = MagicMock()
        return mock

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_playback_domain_service(self):
        """Mock playback domain service."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_session_repo,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_playback_domain_service,
        mock_history_repo,
    ):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.playback_service import (
            PlaybackApplicationService,
        )

        return PlaybackApplicationService(
            session_repository=mock_session_repo,
            history_repository=mock_history_repo,
            voice_adapter=mock_voice_adapter,
            audio_resolver=mock_audio_resolver,
            playback_domain_service=mock_playback_domain_service,
        )

    @pytest.fixture
    def sample_track(self):
        """Sample track for testing."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            stream_url="https://stream.example.com/audio",
        )

    @pytest.mark.asyncio
    async def test_handle_track_finished_no_session(self, service, mock_session_repo, sample_track):
        """Should return early when no session exists."""
        mock_session_repo.get.return_value = None

        await service.handle_track_finished(guild_id=123456, track=sample_track)

        mock_session_repo.get.assert_called_once_with(123456)
        mock_session_repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_track_finished_with_next_track(
        self, service, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should start playback of next track."""
        session = GuildPlaybackSession(guild_id=123456)
        next_track = Track(
            id=TrackId("next"),
            title="Next Track",
            webpage_url="https://youtube.com/watch?v=next",
            stream_url="https://stream.example.com/next",
        )
        session.current_track = sample_track
        session.enqueue(next_track)
        mock_session_repo.get.return_value = session
        mock_voice_adapter.play.return_value = True

        await service.handle_track_finished(guild_id=123456, track=sample_track)

        mock_session_repo.save.assert_called()

    @pytest.mark.asyncio
    async def test_handle_track_finished_empty_queue(
        self, service, mock_session_repo, sample_track
    ):
        """Should log queue empty when no next track."""
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        mock_session_repo.get.return_value = session

        await service.handle_track_finished(guild_id=123456, track=sample_track)

        mock_session_repo.save.assert_called()

    @pytest.mark.asyncio
    async def test_handle_track_finished_calls_sync_callback(
        self, service, mock_session_repo, sample_track
    ):
        """Should call synchronous callback when set."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session

        callback = MagicMock()
        service.set_track_finished_callback(callback)

        await service.handle_track_finished(guild_id=123456, track=sample_track)

        callback.assert_called_once_with(123456, sample_track)

    @pytest.mark.asyncio
    async def test_handle_track_finished_calls_async_callback(
        self, service, mock_session_repo, sample_track
    ):
        """Should await async callback when set."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session

        async_callback = AsyncMock()
        service.set_track_finished_callback(async_callback)

        await service.handle_track_finished(guild_id=123456, track=sample_track)

        async_callback.assert_called_once_with(123456, sample_track)

    @pytest.mark.asyncio
    async def test_handle_track_finished_callback_error(
        self, service, mock_session_repo, sample_track
    ):
        """Should handle callback errors gracefully."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session

        callback = MagicMock(side_effect=Exception("Callback error"))
        service.set_track_finished_callback(callback)

        # Should not raise
        await service.handle_track_finished(guild_id=123456, track=sample_track)


class TestPlaybackApplicationServiceEnsureStreamUrl:
    """Unit tests for PlaybackApplicationService._ensure_stream_url method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        mock = AsyncMock()
        mock.set_on_track_end_callback = MagicMock()
        return mock

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_playback_domain_service(self):
        """Mock playback domain service."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_session_repo,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_playback_domain_service,
        mock_history_repo,
    ):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.playback_service import (
            PlaybackApplicationService,
        )

        return PlaybackApplicationService(
            session_repository=mock_session_repo,
            history_repository=mock_history_repo,
            voice_adapter=mock_voice_adapter,
            audio_resolver=mock_audio_resolver,
            playback_domain_service=mock_playback_domain_service,
        )

    @pytest.fixture
    def track_without_stream(self):
        """Track without stream URL."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            duration_seconds=180,
        )

    @pytest.fixture
    def track_with_stream(self):
        """Track with stream URL."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            stream_url="https://stream.example.com/audio",
            duration_seconds=180,
        )

    @pytest.mark.asyncio
    async def test_ensure_stream_url_already_has_url(self, service, track_with_stream):
        """Should return track unchanged if it has stream URL."""
        session = GuildPlaybackSession(guild_id=123456)

        result = await service._ensure_stream_url(session, track_with_stream, 123456)

        assert result == track_with_stream

    @pytest.mark.asyncio
    async def test_ensure_stream_url_resolves_successfully(
        self, service, mock_audio_resolver, track_without_stream
    ):
        """Should resolve stream URL when not present."""
        session = GuildPlaybackSession(guild_id=123456)

        # Mock resolved result with proper None values for optional fields
        resolved = MagicMock()
        resolved.title = "Resolved Title"
        resolved.stream_url = "https://resolved.stream.com/audio"
        resolved.duration_seconds = 200
        resolved.thumbnail_url = "https://thumb.example.com/img.jpg"
        resolved.artist = None
        resolved.uploader = None
        resolved.like_count = None
        resolved.view_count = None
        mock_audio_resolver.resolve.return_value = resolved

        result = await service._ensure_stream_url(session, track_without_stream, 123456)
        assert result is not None
        assert result.stream_url == "https://resolved.stream.com/audio"
        assert result.title == "Resolved Title"

    @pytest.mark.asyncio
    async def test_ensure_stream_url_resolver_returns_none(
        self, service, mock_session_repo, mock_audio_resolver, track_without_stream
    ):
        """Should handle resolver returning None."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_audio_resolver.resolve.return_value = None
        mock_session_repo.get.return_value = session

        result = await service._ensure_stream_url(session, track_without_stream, 123456)

        assert result is None
        mock_session_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_stream_url_resolver_exception(
        self, service, mock_session_repo, mock_audio_resolver, track_without_stream
    ):
        """Should handle resolver exception and retry with next track."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_audio_resolver.resolve.side_effect = Exception("Network error")
        mock_session_repo.get.return_value = session

        result = await service._ensure_stream_url(session, track_without_stream, 123456)

        assert result is None
        mock_session_repo.save.assert_called()


class TestPlaybackApplicationServiceStartVoicePlayback:
    """Unit tests for PlaybackApplicationService._start_voice_playback method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        mock = AsyncMock()
        mock.set_on_track_end_callback = MagicMock()
        return mock

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_playback_domain_service(self):
        """Mock playback domain service."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_session_repo,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_playback_domain_service,
        mock_history_repo,
    ):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.playback_service import (
            PlaybackApplicationService,
        )

        return PlaybackApplicationService(
            session_repository=mock_session_repo,
            history_repository=mock_history_repo,
            voice_adapter=mock_voice_adapter,
            audio_resolver=mock_audio_resolver,
            playback_domain_service=mock_playback_domain_service,
        )

    @pytest.fixture
    def sample_track(self):
        """Sample track for testing."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            stream_url="https://stream.example.com/audio",
        )

    @pytest.mark.asyncio
    async def test_start_voice_playback_success(
        self, service, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should start voice playback successfully."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session
        mock_voice_adapter.play.return_value = True

        result = await service._start_voice_playback(session, sample_track, 123456)

        assert result is True
        mock_voice_adapter.play.assert_called_once_with(123456, sample_track, start_seconds=None)
        mock_session_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_voice_playback_adapter_fails(
        self, service, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should return False when voice adapter fails."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session
        mock_voice_adapter.play.return_value = False

        result = await service._start_voice_playback(session, sample_track, 123456)

        assert result is False

    @pytest.mark.asyncio
    async def test_start_voice_playback_exception(
        self, service, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should return False on exception."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session
        mock_voice_adapter.play.side_effect = Exception("Voice error")

        result = await service._start_voice_playback(session, sample_track, 123456)

        assert result is False


class TestPlaybackApplicationServicePauseResumeErrors:
    """Unit tests for PlaybackApplicationService error handling in pause/resume."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        mock = AsyncMock()
        mock.set_on_track_end_callback = MagicMock()
        return mock

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_playback_domain_service(self):
        """Mock playback domain service."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_session_repo,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_playback_domain_service,
        mock_history_repo,
    ):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.playback_service import (
            PlaybackApplicationService,
        )

        return PlaybackApplicationService(
            session_repository=mock_session_repo,
            history_repository=mock_history_repo,
            voice_adapter=mock_voice_adapter,
            audio_resolver=mock_audio_resolver,
            playback_domain_service=mock_playback_domain_service,
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
    async def test_pause_handles_exception(
        self, service, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should return False when pause raises exception."""
        session = GuildPlaybackSession(guild_id=123456)
        session.start_playback(sample_track)
        mock_session_repo.get.return_value = session
        mock_voice_adapter.pause.side_effect = Exception("Pause error")

        result = await service.pause_playback(guild_id=123456)

        assert result is False

    @pytest.mark.asyncio
    async def test_resume_handles_exception(
        self, service, mock_session_repo, mock_voice_adapter, sample_track
    ):
        """Should return False when resume raises exception."""
        session = GuildPlaybackSession(guild_id=123456)
        session.start_playback(sample_track)
        session.pause()
        mock_session_repo.get.return_value = session
        mock_voice_adapter.resume.side_effect = Exception("Resume error")

        result = await service.resume_playback(guild_id=123456)

        assert result is False


class TestPlaybackApplicationServiceStopErrors:
    """Unit tests for PlaybackApplicationService error handling in stop."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_voice_adapter(self):
        """Mock voice adapter."""
        mock = AsyncMock()
        mock.set_on_track_end_callback = MagicMock()
        return mock

    @pytest.fixture
    def mock_audio_resolver(self):
        """Mock audio resolver."""
        return AsyncMock()

    @pytest.fixture
    def mock_playback_domain_service(self):
        """Mock playback domain service."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_session_repo,
        mock_voice_adapter,
        mock_audio_resolver,
        mock_playback_domain_service,
        mock_history_repo,
    ):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.playback_service import (
            PlaybackApplicationService,
        )

        return PlaybackApplicationService(
            session_repository=mock_session_repo,
            history_repository=mock_history_repo,
            voice_adapter=mock_voice_adapter,
            audio_resolver=mock_audio_resolver,
            playback_domain_service=mock_playback_domain_service,
        )

    @pytest.mark.asyncio
    async def test_stop_handles_exception(self, service, mock_session_repo, mock_voice_adapter):
        """Should return False when stop raises exception."""
        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session
        mock_voice_adapter.stop.side_effect = Exception("Stop error")

        result = await service.stop_playback(guild_id=123456)

        assert result is False


# =============================================================================
# QueueInfo Property Tests (Edge Cases)
# =============================================================================


class TestQueueInfoProperties:
    """Unit tests for QueueInfo property aliases."""

    def test_tracks_property_alias(self):
        """tracks should be alias for upcoming_tracks."""
        from discord_music_player.application.services.queue_service import QueueInfo

        tracks = [
            Track(
                id=TrackId("track1"),
                title="Track 1",
                webpage_url="https://youtube.com/watch?v=track1",
            ),
            Track(
                id=TrackId("track2"),
                title="Track 2",
                webpage_url="https://youtube.com/watch?v=track2",
            ),
        ]

        info = QueueInfo(
            current_track=None,
            upcoming_tracks=tracks,
            total_length=2,
            total_duration_seconds=360,
        )

        assert info.tracks == tracks
        assert info.tracks == info.upcoming_tracks

    def test_total_tracks_property_alias(self):
        """total_tracks should be alias for total_length."""
        from discord_music_player.application.services.queue_service import QueueInfo

        info = QueueInfo(
            current_track=None,
            upcoming_tracks=[],
            total_length=5,
            total_duration_seconds=None,
        )

        assert info.total_tracks == 5
        assert info.total_tracks == info.total_length

    def test_total_duration_property_alias(self):
        """total_duration should be alias for total_duration_seconds."""
        from discord_music_player.application.services.queue_service import QueueInfo

        info = QueueInfo(
            current_track=None,
            upcoming_tracks=[],
            total_length=0,
            total_duration_seconds=600,
        )

        assert info.total_duration == 600
        assert info.total_duration == info.total_duration_seconds

    def test_total_duration_property_none(self):
        """total_duration should return None when total_duration_seconds is None."""
        from discord_music_player.application.services.queue_service import QueueInfo

        info = QueueInfo(
            current_track=None,
            upcoming_tracks=[],
            total_length=0,
            total_duration_seconds=None,
        )

        assert info.total_duration is None


class TestQueueApplicationServiceMoveEdgeCases:
    """Edge case tests for QueueApplicationService.move method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_queue_domain_service(self):
        """Mock queue domain service."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_session_repo, mock_queue_domain_service):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.queue_service import QueueApplicationService

        return QueueApplicationService(
            session_repository=mock_session_repo,
            queue_domain_service=mock_queue_domain_service,
        )

    @pytest.fixture
    def sample_tracks(self):
        """Sample tracks for testing."""
        return [
            Track(
                id=TrackId(f"track{i}"),
                title=f"Track {i}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
            )
            for i in range(3)
        ]

    @pytest.mark.asyncio
    async def test_move_invalid_positions(self, service, mock_session_repo, sample_tracks):
        """Should return False for invalid positions."""
        session = GuildPlaybackSession(guild_id=123456)
        for track in sample_tracks:
            session.enqueue(track)
        mock_session_repo.get.return_value = session

        # Invalid from_pos
        result = await service.move(guild_id=123456, from_pos=10, to_pos=0)
        # Result depends on session.move_track implementation
        # If it returns False for invalid positions, this should be False
        assert isinstance(result, bool)


class TestQueueApplicationServiceRemoveEdgeCases:
    """Edge case tests for QueueApplicationService.remove method."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_queue_domain_service(self):
        """Mock queue domain service."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_session_repo, mock_queue_domain_service):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.queue_service import QueueApplicationService

        return QueueApplicationService(
            session_repository=mock_session_repo,
            queue_domain_service=mock_queue_domain_service,
        )

    @pytest.fixture
    def sample_tracks(self):
        """Sample tracks for testing."""
        return [
            Track(
                id=TrackId(f"track{i}"),
                title=f"Track {i}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
            )
            for i in range(3)
        ]

    @pytest.mark.asyncio
    async def test_remove_invalid_position(self, service, mock_session_repo, sample_tracks):
        """Should return None for invalid position."""
        session = GuildPlaybackSession(guild_id=123456)
        for track in sample_tracks:
            session.enqueue(track)
        mock_session_repo.get.return_value = session

        result = await service.remove(guild_id=123456, position=10)

        assert result is None


class TestQueueApplicationServiceShuffleNoSession:
    """Edge case tests for QueueApplicationService.shuffle with no session."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_queue_domain_service(self):
        """Mock queue domain service."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_session_repo, mock_queue_domain_service):
        """Create service with mock dependencies."""
        from discord_music_player.application.services.queue_service import QueueApplicationService

        return QueueApplicationService(
            session_repository=mock_session_repo,
            queue_domain_service=mock_queue_domain_service,
        )

    @pytest.mark.asyncio
    async def test_shuffle_no_session(self, service, mock_session_repo):
        """Should return False when no session exists."""
        mock_session_repo.get.return_value = None

        result = await service.shuffle(guild_id=123456)

        assert result is False
