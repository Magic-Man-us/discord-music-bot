"""
Infrastructure Layer Unit Tests

Minimal testing approach: Happy path + Exception handling only.
Tests for audio resolver, ffmpeg player, voice adapter, and cleanup job.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# YtDlpResolver Tests
# ============================================================================


class TestYtDlpResolver:
    """Tests for YtDlpResolver - yt-dlp based audio resolution."""

    @pytest.fixture
    def resolver(self):
        """Create a YtDlpResolver instance with default settings."""
        from discord_music_player.config.settings import AudioSettings
        from discord_music_player.infrastructure.audio.ytdlp_resolver import YtDlpResolver

        settings = AudioSettings()
        return YtDlpResolver(settings=settings)

    @pytest.fixture
    def mock_info_dict(self):
        """Sample yt-dlp info dictionary."""
        return {
            "title": "Test Song",
            "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "url": "https://audio-stream.example.com/stream.mp3",
            "duration": 180,
            "thumbnail": "https://example.com/thumb.jpg",
        }

    # Happy Path Tests

    def test_is_url_with_valid_url(self, resolver):
        """Test that valid URLs are recognized."""
        assert resolver.is_url("https://youtube.com/watch?v=abc123")
        assert resolver.is_url("http://example.com/video")
        assert resolver.is_url("www.youtube.com/watch")

    def test_is_url_with_search_query(self, resolver):
        """Test that search queries are not recognized as URLs."""
        assert not resolver.is_url("never gonna give you up")
        assert not resolver.is_url("test song")

    def test_is_playlist_with_playlist_url(self, resolver):
        """Test that playlist URLs are recognized."""
        assert resolver.is_playlist("https://youtube.com/playlist?list=PLtest123")
        assert resolver.is_playlist("https://youtube.com/watch?v=abc&list=PLtest123")

    def test_is_playlist_with_regular_url(self, resolver):
        """Test that regular URLs are not recognized as playlists."""
        assert not resolver.is_playlist("https://youtube.com/watch?v=abc123")
        assert not resolver.is_playlist("https://example.com/video")

    def test_info_to_track_success(self, resolver, mock_info_dict):
        """Test successful conversion of yt-dlp info to Track entity."""
        track = resolver._info_to_track(mock_info_dict)

        assert track is not None
        assert track.title == "Test Song"
        assert track.webpage_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert track.stream_url == "https://audio-stream.example.com/stream.mp3"
        assert track.duration_seconds == 180

    @pytest.mark.asyncio
    async def test_resolve_url_success(self, resolver, mock_info_dict):
        """Test successful URL resolution to Track."""
        with patch.object(resolver, "_extract_info_sync", return_value=mock_info_dict):
            track = await resolver.resolve("https://youtube.com/watch?v=test")

            assert track is not None
            assert track.title == "Test Song"

    @pytest.mark.asyncio
    async def test_search_success(self, resolver, mock_info_dict):
        """Test successful search returns tracks."""
        with patch.object(resolver, "_search_sync", return_value=[mock_info_dict]):
            tracks = await resolver.search("test query", limit=5)

            assert len(tracks) == 1
            assert tracks[0].title == "Test Song"

    # Exception Tests

    def test_info_to_track_missing_url(self, resolver):
        """Test info conversion fails when URL is missing."""
        info = {"title": "Test"}
        track = resolver._info_to_track(info)
        assert track is None

    def test_info_to_track_missing_stream(self, resolver):
        """Test info conversion fails when stream URL is missing."""
        info = {
            "title": "Test Song",
            "webpage_url": "https://youtube.com/watch?v=test",
            # No 'url' or 'formats' for stream
        }
        track = resolver._info_to_track(info)
        assert track is None

    @pytest.mark.asyncio
    async def test_resolve_returns_none_on_failure(self, resolver):
        """Test resolve returns None when extraction fails."""
        with patch.object(resolver, "_extract_info_sync", return_value=None):
            track = await resolver.resolve("https://youtube.com/watch?v=test")
            assert track is None

    @pytest.mark.asyncio
    async def test_resolve_handles_exception(self, resolver):
        """Test resolve handles exceptions gracefully."""
        with patch.object(resolver, "_extract_info_sync", side_effect=Exception("Network error")):
            track = await resolver.resolve("https://youtube.com/watch?v=test")
            assert track is None

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_failure(self, resolver):
        """Test search returns empty list on failure."""
        with patch.object(resolver, "_search_sync", return_value=[]):
            tracks = await resolver.search("nonexistent query", limit=5)
            assert tracks == []

    @pytest.mark.asyncio
    async def test_search_handles_exception(self, resolver):
        """Test search handles exceptions gracefully."""
        with patch.object(resolver, "_search_sync", side_effect=Exception("Search failed")):
            tracks = await resolver.search("test query", limit=5)
            assert tracks == []


# ============================================================================
# FFmpegPlayer Tests
# ============================================================================


class TestCleanupJob:
    """Tests for CleanupJob - periodic resource cleanup."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock cleanup settings."""
        settings = MagicMock()
        settings.cleanup_interval_minutes = 60
        settings.stale_session_hours = 24
        return settings

    @pytest.fixture
    def mock_repos(self):
        """Create mock repositories."""
        session_repo = AsyncMock()
        session_repo.cleanup_stale = AsyncMock(return_value=5)

        history_repo = AsyncMock()
        history_repo.cleanup_old = AsyncMock(return_value=10)

        cache_repo = AsyncMock()
        cache_repo.cleanup_expired = AsyncMock(return_value=3)

        vote_repo = AsyncMock()
        vote_repo.cleanup_expired = AsyncMock(return_value=2)

        return session_repo, history_repo, cache_repo, vote_repo

    @pytest.fixture
    def cleanup_job(self, mock_repos, mock_settings):
        """Create a CleanupJob instance."""
        from discord_music_player.infrastructure.persistence.cleanup import CleanupJob

        session_repo, history_repo, cache_repo, vote_repo = mock_repos
        return CleanupJob(
            session_repository=session_repo,
            history_repository=history_repo,
            cache_repository=cache_repo,
            vote_repository=vote_repo,
            settings=mock_settings,
        )

    # Happy Path Tests

    @pytest.mark.asyncio
    async def test_run_cleanup_success(self, cleanup_job):
        """Test successful cleanup cycle."""
        stats = await cleanup_job.run_cleanup()

        assert stats.sessions_cleaned == 5
        assert stats.history_cleaned == 10
        assert stats.cache_cleaned == 3
        assert stats.votes_cleaned == 2
        assert stats.total_cleaned == 20

    @pytest.mark.asyncio
    async def test_start_job(self, cleanup_job):
        """Test starting the cleanup job creates background task."""
        assert cleanup_job.is_running is False
        assert cleanup_job._task is None

        # Start the job
        cleanup_job.start()

        assert cleanup_job.is_running is True
        assert cleanup_job._task is not None
        assert not cleanup_job._task.done()

        # Clean up
        await cleanup_job.stop()

    @pytest.mark.asyncio
    async def test_start_job_when_already_running(self, cleanup_job):
        """Test starting job when already running logs warning and returns."""
        # Start the job
        cleanup_job.start()
        initial_task = cleanup_job._task

        # Try to start again
        cleanup_job.start()

        # Should still be the same task (not restarted)
        assert cleanup_job._task is initial_task
        assert cleanup_job.is_running is True

        # Clean up
        await cleanup_job.stop()

    @pytest.mark.asyncio
    async def test_stop_job(self, cleanup_job):
        """Test stopping the cleanup job cancels the task."""
        # Start the job
        cleanup_job.start()
        assert cleanup_job.is_running is True

        # Stop the job
        await cleanup_job.stop()

        assert cleanup_job.is_running is False
        assert cleanup_job._task is None

    @pytest.mark.asyncio
    async def test_stop_job_when_not_running(self, cleanup_job):
        """Test stopping job when not running is safe."""
        assert cleanup_job.is_running is False

        # Should not raise exception
        await cleanup_job.stop()

        assert cleanup_job.is_running is False

    @pytest.mark.asyncio
    async def test_run_loop_executes_cleanup(self, cleanup_job, mock_repos):
        """Test that run loop executes cleanup periodically."""
        session_repo, history_repo, cache_repo, vote_repo = mock_repos

        # Set very short interval for testing
        cleanup_job._settings.cleanup_interval_minutes = 0.01  # 0.6 seconds

        # Start the job
        cleanup_job.start()

        # Wait for at least one cleanup cycle
        await asyncio.sleep(1)

        # Stop the job
        await cleanup_job.stop()

        # Verify cleanup was called at least once
        session_repo.cleanup_stale.assert_called()
        history_repo.cleanup_old.assert_called()
        cache_repo.cleanup_expired.assert_called()
        vote_repo.cleanup_expired.assert_called()

    @pytest.mark.asyncio
    async def test_run_loop_handles_cleanup_exception(self, cleanup_job):
        """Test that run loop continues after cleanup exception in run_cleanup itself."""
        # Mock run_cleanup to raise an exception that isn't caught internally
        original_run_cleanup = cleanup_job.run_cleanup
        call_count = 0

        async def mock_run_cleanup():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call raises unhandled exception
                raise RuntimeError("Unexpected error in run_cleanup")
            # Second call succeeds
            return await original_run_cleanup()

        cleanup_job.run_cleanup = mock_run_cleanup

        # Set very short interval
        cleanup_job._settings.cleanup_interval_minutes = 0.01

        # Start the job
        cleanup_job.start()

        # Wait for multiple cycles
        await asyncio.sleep(1.5)

        # Stop the job
        await cleanup_job.stop()

        # Verify cleanup was called multiple times despite exception
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_run_loop_stops_on_cancel(self, cleanup_job):
        """Test that run loop exits cleanly when cancelled."""
        # Set long interval so we're waiting when we cancel
        cleanup_job._settings.cleanup_interval_minutes = 60

        # Start the job
        cleanup_job.start()
        task = cleanup_job._task

        # Give it a moment to enter the sleep
        await asyncio.sleep(0.1)

        # Stop should cancel cleanly
        await cleanup_job.stop()

        # Task should be done (catches CancelledError and exits cleanly)
        assert task.done()
        # Note: task.cancelled() is False because _run_loop catches CancelledError and exits normally

    def test_cleanup_stats_to_dict(self):
        """Test CleanupStats to_dict method."""
        from discord_music_player.infrastructure.persistence.cleanup import CleanupStats

        stats = CleanupStats()
        stats.sessions_cleaned = 5
        stats.history_cleaned = 10
        stats.cache_cleaned = 3
        stats.votes_cleaned = 2

        result = stats.to_dict()

        assert result["sessions"] == 5
        assert result["history"] == 10
        assert result["cache"] == 3
        assert result["votes"] == 2
        assert result["total"] == 20

    # Exception Tests

    @pytest.mark.asyncio
    async def test_cleanup_handles_session_error(self, cleanup_job, mock_repos):
        """Test cleanup handles session repository errors."""
        session_repo, _, _, _ = mock_repos
        session_repo.cleanup_stale.side_effect = Exception("DB error")

        # Should not raise, just log the error
        stats = await cleanup_job.run_cleanup()

        assert stats.sessions_cleaned == 0
        # Other cleanups should still work
        assert stats.history_cleaned == 10
        assert stats.cache_cleaned == 3
        assert stats.votes_cleaned == 2

    @pytest.mark.asyncio
    async def test_cleanup_handles_history_error(self, cleanup_job, mock_repos):
        """Test cleanup handles history repository errors."""
        _, history_repo, _, _ = mock_repos
        history_repo.cleanup_old.side_effect = Exception("DB error")

        stats = await cleanup_job.run_cleanup()

        assert stats.sessions_cleaned == 5
        assert stats.history_cleaned == 0
        assert stats.cache_cleaned == 3
        assert stats.votes_cleaned == 2

    @pytest.mark.asyncio
    async def test_cleanup_handles_cache_error(self, cleanup_job, mock_repos):
        """Test cleanup handles cache repository errors."""
        _, _, cache_repo, _ = mock_repos
        cache_repo.cleanup_expired.side_effect = Exception("Cache error")

        stats = await cleanup_job.run_cleanup()

        assert stats.sessions_cleaned == 5
        assert stats.history_cleaned == 10
        assert stats.cache_cleaned == 0
        assert stats.votes_cleaned == 2

    @pytest.mark.asyncio
    async def test_cleanup_handles_vote_error(self, cleanup_job, mock_repos):
        """Test cleanup handles vote repository errors."""
        _, _, _, vote_repo = mock_repos
        vote_repo.cleanup_expired.side_effect = Exception("Vote error")

        stats = await cleanup_job.run_cleanup()

        assert stats.sessions_cleaned == 5
        assert stats.history_cleaned == 10
        assert stats.cache_cleaned == 3
        assert stats.votes_cleaned == 0

    def test_is_running_property(self, cleanup_job):
        """Test is_running property reflects _running state."""
        assert cleanup_job.is_running is False

        cleanup_job._running = True
        assert cleanup_job.is_running is True

        cleanup_job._running = False
        assert cleanup_job.is_running is False


# ============================================================================
# DiscordVoiceAdapter Tests
# ============================================================================


class TestDiscordVoiceAdapter:
    """Tests for DiscordVoiceAdapter - Discord voice operations."""

    @pytest.fixture
    def mock_bot(self):
        """Create a mock Discord bot."""
        bot = MagicMock()
        bot.loop = asyncio.new_event_loop()
        return bot

    @pytest.fixture
    def adapter(self, mock_bot):
        """Create a DiscordVoiceAdapter instance."""
        from discord_music_player.config.settings import AudioSettings
        from discord_music_player.infrastructure.discord.adapters.voice_adapter import (
            DiscordVoiceAdapter,
        )

        settings = AudioSettings()
        return DiscordVoiceAdapter(bot=mock_bot, settings=settings)

    @pytest.fixture
    def mock_voice_client(self):
        """Create a mock voice client."""
        import discord

        vc = MagicMock(spec=discord.VoiceClient)
        vc.is_connected.return_value = True
        vc.is_playing.return_value = False
        vc.is_paused.return_value = False
        vc.channel = MagicMock()
        vc.channel.id = 12345
        vc.stop = MagicMock()
        vc.pause = MagicMock()
        vc.resume = MagicMock()
        vc.play = MagicMock()
        vc.disconnect = AsyncMock()
        return vc

    @pytest.fixture
    def mock_track(self):
        """Create a mock Track entity."""
        from discord_music_player.domain.music.entities import Track
        from discord_music_player.domain.music.value_objects import TrackId

        return Track(
            id=TrackId(value="test123"),
            title="Test Song",
            webpage_url="https://youtube.com/watch?v=test",
            stream_url="https://audio.example.com/stream.mp3",
            duration_seconds=180,
        )

    # Happy Path Tests

    def test_is_connected_when_connected(self, adapter, mock_bot, mock_voice_client):
        """Test is_connected returns True when connected."""
        guild = MagicMock()
        guild.voice_client = mock_voice_client
        mock_bot.get_guild.return_value = guild

        result = adapter.is_connected(123456)
        assert result is True

    def test_is_connected_when_not_connected(self, adapter, mock_bot):
        """Test is_connected returns False when not connected."""
        mock_bot.get_guild.return_value = None

        result = adapter.is_connected(123456)
        assert result is False

    def test_is_playing_when_playing(self, adapter, mock_bot, mock_voice_client):
        """Test is_playing returns True when playing."""
        mock_voice_client.is_playing.return_value = True

        guild = MagicMock()
        guild.voice_client = mock_voice_client
        mock_bot.get_guild.return_value = guild

        result = adapter.is_playing(123456)
        assert result is True

    def test_is_paused_when_paused(self, adapter, mock_bot, mock_voice_client):
        """Test is_paused returns True when paused."""
        mock_voice_client.is_paused.return_value = True

        guild = MagicMock()
        guild.voice_client = mock_voice_client
        mock_bot.get_guild.return_value = guild

        result = adapter.is_paused(123456)
        assert result is True

    def test_get_current_channel_id(self, adapter, mock_bot, mock_voice_client):
        """Test getting current voice channel ID."""
        guild = MagicMock()
        guild.voice_client = mock_voice_client
        mock_bot.get_guild.return_value = guild

        result = adapter.get_current_channel_id(123456)
        assert result == 12345

    @pytest.mark.asyncio
    async def test_disconnect_success(self, adapter, mock_bot, mock_voice_client):
        """Test successful voice disconnect."""
        guild = MagicMock()
        guild.voice_client = mock_voice_client
        mock_bot.get_guild.return_value = guild

        result = await adapter.disconnect(123456)

        assert result is True
        mock_voice_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_success(self, adapter, mock_bot, mock_voice_client):
        """Test successful playback stop."""
        mock_voice_client.is_playing.return_value = True

        guild = MagicMock()
        guild.voice_client = mock_voice_client
        mock_bot.get_guild.return_value = guild

        result = await adapter.stop(123456)

        assert result is True
        mock_voice_client.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_success(self, adapter, mock_bot, mock_voice_client):
        """Test successful playback pause."""
        mock_voice_client.is_playing.return_value = True

        guild = MagicMock()
        guild.voice_client = mock_voice_client
        mock_bot.get_guild.return_value = guild

        result = await adapter.pause(123456)

        assert result is True
        mock_voice_client.pause.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_success(self, adapter, mock_bot, mock_voice_client):
        """Test successful playback resume."""
        mock_voice_client.is_paused.return_value = True

        guild = MagicMock()
        guild.voice_client = mock_voice_client
        mock_bot.get_guild.return_value = guild

        result = await adapter.resume(123456)

        assert result is True
        mock_voice_client.resume.assert_called_once()

    def test_get_current_track_returns_none(self, adapter):
        """Test get_current_track returns None when no track playing."""
        result = adapter.get_current_track(123456)
        assert result is None

    def test_set_on_track_end_callback(self, adapter):
        """Test setting track end callback."""
        callback = AsyncMock()
        adapter.set_on_track_end_callback(callback)

        assert adapter._on_track_end == callback

    # Exception Tests

    @pytest.mark.asyncio
    async def test_connect_guild_not_found(self, adapter, mock_bot):
        """Test connect fails when guild not found."""
        mock_bot.get_guild.return_value = None

        result = await adapter.connect(123456, 789012)
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_invalid_channel(self, adapter, mock_bot):
        """Test connect fails when channel is not a voice channel."""
        guild = MagicMock()
        guild.get_channel.return_value = MagicMock(spec=[])  # Not a VoiceChannel
        mock_bot.get_guild.return_value = guild

        result = await adapter.connect(123456, 789012)
        assert result is False

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, adapter, mock_bot):
        """Test disconnect returns True when not connected."""
        mock_bot.get_guild.return_value = None

        result = await adapter.disconnect(123456)
        assert result is True  # Idempotent - not connected is success

    @pytest.mark.asyncio
    async def test_pause_when_not_playing(self, adapter, mock_bot, mock_voice_client):
        """Test pause returns False when not playing."""
        mock_voice_client.is_playing.return_value = False

        guild = MagicMock()
        guild.voice_client = mock_voice_client
        mock_bot.get_guild.return_value = guild

        result = await adapter.pause(123456)
        assert result is False

    @pytest.mark.asyncio
    async def test_resume_when_not_paused(self, adapter, mock_bot, mock_voice_client):
        """Test resume returns False when not paused."""
        mock_voice_client.is_paused.return_value = False

        guild = MagicMock()
        guild.voice_client = mock_voice_client
        mock_bot.get_guild.return_value = guild

        result = await adapter.resume(123456)
        assert result is False

    @pytest.mark.asyncio
    async def test_play_not_connected(self, adapter, mock_bot, mock_track):
        """Test play fails when not connected to voice."""
        mock_bot.get_guild.return_value = None

        result = await adapter.play(123456, mock_track)
        assert result is False

    @pytest.mark.asyncio
    async def test_play_no_stream_url(self, adapter, mock_bot, mock_voice_client):
        """Test play fails when track has no stream URL."""
        from discord_music_player.domain.music.entities import Track
        from discord_music_player.domain.music.value_objects import TrackId

        track = Track(
            id=TrackId(value="test123"),
            title="No Stream",
            webpage_url="https://youtube.com/watch",
            stream_url=None,
        )

        guild = MagicMock()
        guild.voice_client = mock_voice_client
        mock_bot.get_guild.return_value = guild

        result = await adapter.play(123456, track)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_listeners_not_connected(self, adapter, mock_bot):
        """Test get_listeners returns empty list when not connected."""
        mock_bot.get_guild.return_value = None

        result = await adapter.get_listeners(123456)
        assert result == []

    def test_set_volume_not_connected(self, adapter, mock_bot):
        """Test set_volume returns False when not connected."""
        mock_bot.get_guild.return_value = None

        result = adapter.set_volume(123456, 0.5)
        assert result is False

    def test_get_current_channel_id_not_connected(self, adapter, mock_bot):
        """Test get_current_channel_id returns None when not connected."""
        mock_bot.get_guild.return_value = None

        result = adapter.get_current_channel_id(123456)
        assert result is None


# ============================================================================
# FFmpegConfig Tests
# ============================================================================


class TestFFmpegConfig:
    """Tests for FFmpegConfig - FFmpeg audio configuration."""

    def test_default_config(self):
        """Test default FFmpeg configuration."""
        from discord_music_player.infrastructure.audio.ffmpeg_player import FFmpegConfig

        config = FFmpegConfig()

        assert config.reconnect is True
        assert config.reconnect_streamed is True
        assert config.reconnect_delay_max == 5
        assert config.disable_video is True
        assert config.default_volume == 0.5

    def test_get_before_options(self):
        """Test getting FFmpeg before options."""
        from discord_music_player.infrastructure.audio.ffmpeg_player import FFmpegConfig

        config = FFmpegConfig()
        opts = config.get_before_options()

        assert "-reconnect 1" in opts
        assert "-reconnect_streamed 1" in opts
        assert "-reconnect_delay_max 5" in opts

    def test_get_options(self):
        """Test getting FFmpeg options."""
        from discord_music_player.infrastructure.audio.ffmpeg_player import FFmpegConfig

        config = FFmpegConfig()
        opts = config.get_options()

        assert "-vn" in opts
        assert "afade" in opts


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestYtDlpHelpers:
    """Tests for yt-dlp helper functions."""

    def test_generate_track_id_youtube(self):
        """Test generating track ID from YouTube URL."""
        from discord_music_player.infrastructure.audio.ytdlp_resolver import _generate_track_id

        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        track_id = _generate_track_id(url, "Test Song")

        # Should extract the YouTube video ID
        assert track_id == "dQw4w9WgXcQ"

    def test_generate_track_id_non_youtube(self):
        """Test generating track ID from non-YouTube URL."""
        from discord_music_player.infrastructure.audio.ytdlp_resolver import _generate_track_id

        url = "https://example.com/some-audio.mp3"
        track_id = _generate_track_id(url, "Test Song")

        # Should return hash of URL
        assert len(track_id) == 16
        assert track_id.isalnum()
