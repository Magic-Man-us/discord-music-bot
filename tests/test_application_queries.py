"""
Unit Tests for Application Layer Queries

Tests for:
- GetCurrentTrackQuery, GetCurrentTrackHandler, CurrentTrackInfo
- GetQueueQuery, GetQueueHandler, QueueInfo

Uses mocking to isolate from infrastructure dependencies.
"""

from unittest.mock import AsyncMock

import pytest

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.value_objects import PlaybackState, TrackId

# =============================================================================
# GetCurrentTrack Query Tests
# =============================================================================


class TestGetCurrentTrackQuery:
    """Unit tests for GetCurrentTrackQuery."""

    def test_create_query(self):
        """Should create query with guild_id."""
        from discord_music_player.application.queries.get_current import GetCurrentTrackQuery

        query = GetCurrentTrackQuery(guild_id=123456)
        assert query.guild_id == 123456


class TestCurrentTrackInfo:
    """Unit tests for CurrentTrackInfo dataclass."""

    @pytest.fixture
    def sample_track(self):
        """Sample track for testing."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            duration_seconds=180,
        )

    def test_create_with_track(self, sample_track):
        """Should create info with track data."""
        from discord_music_player.application.queries.get_current import CurrentTrackInfo

        info = CurrentTrackInfo(
            guild_id=123456,
            track=sample_track,
            is_playing=True,
            is_paused=False,
            queue_length=5,
        )
        assert info.guild_id == 123456
        assert info.track == sample_track
        assert info.is_playing is True
        assert info.is_paused is False
        assert info.queue_length == 5

    def test_create_without_track(self):
        """Should create info without track (nothing playing)."""
        from discord_music_player.application.queries.get_current import CurrentTrackInfo

        info = CurrentTrackInfo(
            guild_id=123456,
            track=None,
            is_playing=False,
            is_paused=False,
            queue_length=0,
        )
        assert info.track is None
        assert info.is_playing is False


class TestGetCurrentTrackHandler:
    """Unit tests for GetCurrentTrackHandler."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def handler(self, mock_session_repo):
        """Create handler with mock dependencies."""
        from discord_music_player.application.queries.get_current import GetCurrentTrackHandler

        return GetCurrentTrackHandler(session_repository=mock_session_repo)

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
    async def test_handle_no_session(self, handler, mock_session_repo):
        """Should return empty info when no session exists."""
        from discord_music_player.application.queries.get_current import GetCurrentTrackQuery

        mock_session_repo.get.return_value = None
        query = GetCurrentTrackQuery(guild_id=123456)

        result = await handler.handle(query)

        assert result.guild_id == 123456
        assert result.track is None
        assert result.is_playing is False
        assert result.is_paused is False
        assert result.queue_length == 0

    @pytest.mark.asyncio
    async def test_handle_with_session_no_track(self, handler, mock_session_repo):
        """Should return info from session with no current track."""
        from discord_music_player.application.queries.get_current import GetCurrentTrackQuery

        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session
        query = GetCurrentTrackQuery(guild_id=123456)

        result = await handler.handle(query)

        assert result.guild_id == 123456
        assert result.track is None
        assert result.is_playing is False
        assert result.queue_length == 0

    @pytest.mark.asyncio
    async def test_handle_with_current_track_playing(
        self, handler, mock_session_repo, sample_track
    ):
        """Should return info with current track when playing."""
        from discord_music_player.application.queries.get_current import GetCurrentTrackQuery

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        session.state = PlaybackState.PLAYING
        mock_session_repo.get.return_value = session

        query = GetCurrentTrackQuery(guild_id=123456)

        result = await handler.handle(query)

        assert result.guild_id == 123456
        assert result.track == sample_track
        assert result.is_playing is True
        assert result.is_paused is False

    @pytest.mark.asyncio
    async def test_handle_with_current_track_paused(self, handler, mock_session_repo, sample_track):
        """Should return info with current track when paused."""
        from discord_music_player.application.queries.get_current import GetCurrentTrackQuery

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_track
        session.state = PlaybackState.PAUSED
        mock_session_repo.get.return_value = session

        query = GetCurrentTrackQuery(guild_id=123456)

        result = await handler.handle(query)

        assert result.is_playing is False
        assert result.is_paused is True

    @pytest.mark.asyncio
    async def test_handle_includes_queue_length(self, handler, mock_session_repo, sample_track):
        """Should include queue length in result."""
        from discord_music_player.application.queries.get_current import GetCurrentTrackQuery

        session = GuildPlaybackSession(guild_id=123456)
        # Add multiple tracks to queue
        for i in range(3):
            track = Track(
                id=TrackId(f"track{i}"),
                title=f"Track {i}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
            )
            session.enqueue(track)
        mock_session_repo.get.return_value = session

        query = GetCurrentTrackQuery(guild_id=123456)

        result = await handler.handle(query)

        assert result.queue_length == 3


# =============================================================================
# GetQueue Query Tests
# =============================================================================


class TestGetQueueQuery:
    """Unit tests for GetQueueQuery."""

    def test_create_query(self):
        """Should create query with guild_id."""
        from discord_music_player.application.queries.get_queue import GetQueueQuery

        query = GetQueueQuery(guild_id=123456)
        assert query.guild_id == 123456


class TestQueueInfo:
    """Unit tests for QueueInfo dataclass."""

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

    def test_create_with_tracks(self, sample_tracks):
        """Should create info with track list."""
        from discord_music_player.application.queries.get_queue import QueueInfo

        info = QueueInfo(
            guild_id=123456,
            tracks=sample_tracks,
            current_track=sample_tracks[0],
            total_duration=600,
        )
        assert info.guild_id == 123456
        assert len(info.tracks) == 3
        assert info.current_track == sample_tracks[0]
        assert info.total_duration == 600

    def test_create_empty(self):
        """Should create empty queue info."""
        from discord_music_player.application.queries.get_queue import QueueInfo

        info = QueueInfo(
            guild_id=123456,
            tracks=[],
            current_track=None,
            total_duration=0,
        )
        assert info.tracks == []
        assert info.current_track is None

    def test_length_property(self, sample_tracks):
        """length property should return track count."""
        from discord_music_player.application.queries.get_queue import QueueInfo

        info = QueueInfo(
            guild_id=123456,
            tracks=sample_tracks,
            current_track=None,
            total_duration=None,
        )
        assert info.length == 3

    def test_is_empty_property_with_tracks(self, sample_tracks):
        """is_empty should be False when tracks exist."""
        from discord_music_player.application.queries.get_queue import QueueInfo

        info = QueueInfo(
            guild_id=123456,
            tracks=sample_tracks,
            current_track=None,
            total_duration=None,
        )
        assert info.is_empty is False

    def test_is_empty_property_without_tracks(self):
        """is_empty should be True when no tracks."""
        from discord_music_player.application.queries.get_queue import QueueInfo

        info = QueueInfo(
            guild_id=123456,
            tracks=[],
            current_track=None,
            total_duration=None,
        )
        assert info.is_empty is True


class TestGetQueueHandler:
    """Unit tests for GetQueueHandler."""

    @pytest.fixture
    def mock_session_repo(self):
        """Mock session repository."""
        return AsyncMock()

    @pytest.fixture
    def handler(self, mock_session_repo):
        """Create handler with mock dependencies."""
        from discord_music_player.application.queries.get_queue import GetQueueHandler

        return GetQueueHandler(session_repository=mock_session_repo)

    @pytest.fixture
    def sample_tracks(self):
        """Sample tracks with durations for testing."""
        return [
            Track(
                id=TrackId(f"track{i}"),
                title=f"Track {i}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
                duration_seconds=180 + i * 30,  # 180, 210, 240 seconds
            )
            for i in range(3)
        ]

    @pytest.mark.asyncio
    async def test_handle_no_session(self, handler, mock_session_repo):
        """Should return empty queue info when no session exists."""
        from discord_music_player.application.queries.get_queue import GetQueueQuery

        mock_session_repo.get.return_value = None
        query = GetQueueQuery(guild_id=123456)

        result = await handler.handle(query)

        assert result.guild_id == 123456
        assert result.tracks == []
        assert result.current_track is None
        assert result.total_duration == 0

    @pytest.mark.asyncio
    async def test_handle_with_empty_queue(self, handler, mock_session_repo):
        """Should return empty queue info from empty session."""
        from discord_music_player.application.queries.get_queue import GetQueueQuery

        session = GuildPlaybackSession(guild_id=123456)
        mock_session_repo.get.return_value = session
        query = GetQueueQuery(guild_id=123456)

        result = await handler.handle(query)

        assert result.guild_id == 123456
        assert result.tracks == []
        assert result.is_empty is True

    @pytest.mark.asyncio
    async def test_handle_with_tracks(self, handler, mock_session_repo, sample_tracks):
        """Should return queue info with tracks."""
        from discord_music_player.application.queries.get_queue import GetQueueQuery

        session = GuildPlaybackSession(guild_id=123456)
        for track in sample_tracks:
            session.enqueue(track)
        mock_session_repo.get.return_value = session

        query = GetQueueQuery(guild_id=123456)

        result = await handler.handle(query)

        assert len(result.tracks) == 3
        assert result.is_empty is False

    @pytest.mark.asyncio
    async def test_handle_includes_current_track(self, handler, mock_session_repo, sample_tracks):
        """Should include current track in result."""
        from discord_music_player.application.queries.get_queue import GetQueueQuery

        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = sample_tracks[0]
        session.enqueue(sample_tracks[1])
        session.enqueue(sample_tracks[2])
        mock_session_repo.get.return_value = session

        query = GetQueueQuery(guild_id=123456)

        result = await handler.handle(query)

        assert result.current_track == sample_tracks[0]
        assert len(result.tracks) == 2  # Only queued tracks, not current

    @pytest.mark.asyncio
    async def test_handle_calculates_total_duration(
        self, handler, mock_session_repo, sample_tracks
    ):
        """Should calculate total duration of all tracks."""
        from discord_music_player.application.queries.get_queue import GetQueueQuery

        session = GuildPlaybackSession(guild_id=123456)
        for track in sample_tracks:
            session.enqueue(track)
        mock_session_repo.get.return_value = session

        query = GetQueueQuery(guild_id=123456)

        result = await handler.handle(query)

        # 180 + 210 + 240 = 630
        assert result.total_duration == 630

    @pytest.mark.asyncio
    async def test_handle_duration_with_unknown_track(self, handler, mock_session_repo):
        """Should handle tracks with unknown duration."""
        from discord_music_player.application.queries.get_queue import GetQueueQuery

        session = GuildPlaybackSession(guild_id=123456)

        # Track with known duration
        track1 = Track(
            id=TrackId("track1"),
            title="Track 1",
            webpage_url="https://youtube.com/watch?v=track1",
            duration_seconds=180,
        )
        # Track without duration
        track2 = Track(
            id=TrackId("track2"),
            title="Track 2",
            webpage_url="https://youtube.com/watch?v=track2",
            duration_seconds=None,
        )
        session.enqueue(track1)
        session.enqueue(track2)
        mock_session_repo.get.return_value = session

        query = GetQueueQuery(guild_id=123456)

        result = await handler.handle(query)

        # Should still return a duration (sum of known)
        assert result.total_duration == 180
