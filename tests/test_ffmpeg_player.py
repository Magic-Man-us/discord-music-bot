"""
Tests for FFmpegPlayer - Audio Playback Engine

Tests for the FFmpeg-based audio player including:
- Player state management
- Audio source creation
- Playback control (play, pause, resume, stop)
- Volume control
- Resource cleanup
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_music_player.config.settings import AudioSettings
from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.infrastructure.audio.ffmpeg_player import (
    FFmpegConfig,
    FFmpegPlayer,
    PlayerState,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def audio_settings():
    """Create audio settings."""
    return AudioSettings(default_volume=0.5)


@pytest.fixture
def ffmpeg_config():
    """Create FFmpeg config."""
    return FFmpegConfig(
        reconnect=True,
        reconnect_streamed=True,
        reconnect_delay_max=5,
        disable_video=True,
        fade_in_seconds=0.5,
        default_volume=0.5,
    )


@pytest.fixture
def player(audio_settings, ffmpeg_config):
    """Create FFmpeg player."""
    return FFmpegPlayer(audio_settings, ffmpeg_config)


@pytest.fixture
def mock_track():
    """Create a mock track."""
    return Track(
        id=TrackId(value="test123"),
        title="Test Song",
        webpage_url="https://youtube.com/watch?v=test",
        stream_url="https://example.com/audio.m4a",
        duration_seconds=180,
    )


@pytest.fixture
def mock_voice_client():
    """Create a mock Discord voice client."""
    client = MagicMock(spec=discord.VoiceClient)
    client.is_playing.return_value = False
    client.is_paused.return_value = False
    client.source = None
    return client


# =============================================================================
# FFmpegConfig Tests
# =============================================================================


class TestFFmpegConfig:
    """Tests for FFmpeg configuration."""

    def test_get_before_options_all_enabled(self):
        """Should generate before_options with all reconnect settings."""
        config = FFmpegConfig(
            reconnect=True,
            reconnect_streamed=True,
            reconnect_delay_max=10,
        )

        options = config.get_before_options()

        assert "-reconnect 1" in options
        assert "-reconnect_streamed 1" in options
        assert "-reconnect_delay_max 10" in options

    def test_get_before_options_minimal(self):
        """Should handle minimal before_options."""
        config = FFmpegConfig(
            reconnect=False,
            reconnect_streamed=False,
            reconnect_delay_max=0,
        )

        options = config.get_before_options()

        assert options == ""

    def test_get_options_with_video_and_fade(self):
        """Should generate options with video disable and fade."""
        config = FFmpegConfig(
            disable_video=True,
            fade_in_seconds=1.5,
        )

        options = config.get_options()

        assert "-vn" in options
        assert "afade=t=in:ss=0:d=1.5" in options

    def test_get_options_no_fade(self):
        """Should not add fade when duration is 0."""
        config = FFmpegConfig(
            disable_video=True,
            fade_in_seconds=0,
        )

        options = config.get_options()

        assert "-vn" in options
        assert "afade" not in options


# =============================================================================
# Player Initialization Tests
# =============================================================================


class TestPlayerInitialization:
    """Tests for player initialization."""

    def test_init_with_settings_and_config(self, audio_settings, ffmpeg_config):
        """Should initialize with provided settings and config."""
        player = FFmpegPlayer(audio_settings, ffmpeg_config)

        assert player._settings == audio_settings
        assert player._config == ffmpeg_config
        assert len(player._active_sources) == 0
        assert len(player._states) == 0

    def test_init_with_defaults(self):
        """Should initialize with default settings."""
        player = FFmpegPlayer()

        assert player._settings is not None
        assert player._config is not None
        assert player._config.default_volume == player._settings.default_volume

    def test_init_creates_empty_tracking_dicts(self, player):
        """Should initialize empty tracking dictionaries."""
        assert isinstance(player._active_sources, dict)
        assert isinstance(player._active_processes, dict)
        assert isinstance(player._states, dict)
        assert player._on_error is None


# =============================================================================
# Audio Source Creation Tests
# =============================================================================


class TestCreateSource:
    """Tests for audio source creation."""

    def test_create_source_success(self, player, mock_track):
        """Should create audio source with volume transformer."""
        with (
            patch("discord.FFmpegPCMAudio") as mock_ffmpeg,
            patch("discord.PCMVolumeTransformer") as mock_volume,
        ):
            mock_ffmpeg.return_value = MagicMock()
            mock_volume.return_value = MagicMock()

            source = player.create_source(mock_track, volume=0.8)

            mock_ffmpeg.assert_called_once()
            mock_volume.assert_called_once()
            assert mock_volume.call_args[1]["volume"] == 0.8

    def test_create_source_uses_default_volume(self, player, mock_track):
        """Should use default volume when not specified."""
        with (
            patch("discord.FFmpegPCMAudio") as mock_ffmpeg,
            patch("discord.PCMVolumeTransformer") as mock_volume,
        ):
            mock_ffmpeg.return_value = MagicMock()
            mock_volume.return_value = MagicMock()

            player.create_source(mock_track)

            assert mock_volume.call_args[1]["volume"] == 0.5

    def test_create_source_no_stream_url(self, player):
        """Should raise ValueError when track has no stream URL."""
        track = Track(
            id=TrackId(value="test"),
            title="Test",
            webpage_url="https://youtube.com/watch?v=test",
            stream_url=None,
        )

        with pytest.raises(ValueError, match="has no stream URL"):
            player.create_source(track)

    def test_create_source_uses_config_options(self, player, mock_track):
        """Should pass config options to FFmpegPCMAudio."""
        with (
            patch("discord.FFmpegPCMAudio") as mock_ffmpeg,
            patch("discord.PCMVolumeTransformer") as mock_volume,
        ):
            mock_audio_source = MagicMock(spec=discord.AudioSource)
            mock_ffmpeg.return_value = mock_audio_source
            mock_volume.return_value = MagicMock()

            player.create_source(mock_track)

            call_args = mock_ffmpeg.call_args
            assert "before_options" in call_args[1]
            assert "options" in call_args[1]


# =============================================================================
# Playback Control Tests
# =============================================================================


class TestPlayback:
    """Tests for playback control."""

    @pytest.mark.asyncio
    async def test_play_success(self, player, mock_voice_client, mock_track):
        """Should start playback successfully."""
        with (
            patch.object(player, "create_source") as mock_create,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_source = MagicMock()
            mock_create.return_value = mock_source

            result = await player.play(mock_voice_client, mock_track, guild_id=123)

            assert result is True
            mock_voice_client.play.assert_called_once()
            assert player.get_state(123) == PlayerState.PLAYING

    @pytest.mark.asyncio
    async def test_play_stops_current_playback(self, player, mock_voice_client, mock_track):
        """Should stop current playback before starting new one."""
        mock_voice_client.is_playing.return_value = True

        with (
            patch.object(player, "create_source", return_value=MagicMock()),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await player.play(mock_voice_client, mock_track, guild_id=123)

            mock_voice_client.stop.assert_called_once()
            mock_sleep.assert_called()

    @pytest.mark.asyncio
    async def test_play_handles_discord_exception(self, player, mock_voice_client, mock_track):
        """Should handle Discord client exceptions."""
        mock_voice_client.play.side_effect = discord.ClientException("Connection lost")

        with patch.object(player, "create_source", return_value=MagicMock()):
            result = await player.play(mock_voice_client, mock_track, guild_id=123)

            assert result is False
            assert player.get_state(123) == PlayerState.ERROR

    @pytest.mark.asyncio
    async def test_play_handles_general_exception(self, player, mock_voice_client, mock_track):
        """Should handle general exceptions."""
        with patch.object(player, "create_source", side_effect=RuntimeError("FFmpeg error")):
            result = await player.play(mock_voice_client, mock_track, guild_id=123)

            assert result is False
            assert player.get_state(123) == PlayerState.ERROR

    @pytest.mark.asyncio
    async def test_play_calls_after_callback(self, player, mock_voice_client, mock_track):
        """Should call after callback when playback ends."""
        after_callback = MagicMock()

        with patch.object(player, "create_source", return_value=MagicMock()):
            await player.play(mock_voice_client, mock_track, guild_id=123, after=after_callback)

            # Get the cleanup callback that was passed to voice_client.play
            call_args = mock_voice_client.play.call_args
            cleanup_cb = call_args[1]["after"]

            # Simulate playback ending
            cleanup_cb(None)

            after_callback.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_play_error_callback_on_playback_error(
        self, player, mock_voice_client, mock_track
    ):
        """Should call error handler on playback error."""
        error_handler = MagicMock()
        player.set_error_handler(error_handler)

        with patch.object(player, "create_source", return_value=MagicMock()):
            await player.play(mock_voice_client, mock_track, guild_id=123)

            # Get cleanup callback and simulate error
            cleanup_cb = mock_voice_client.play.call_args[1]["after"]
            test_error = Exception("Stream error")
            cleanup_cb(test_error)

            error_handler.assert_called_once_with(123, test_error)

    def test_stop_success(self, player, mock_voice_client):
        """Should stop playback successfully."""
        mock_voice_client.is_playing.return_value = True

        result = player.stop(mock_voice_client, guild_id=123)

        assert result is True
        mock_voice_client.stop.assert_called_once()
        assert player.get_state(123) == PlayerState.IDLE

    def test_stop_when_paused(self, player, mock_voice_client):
        """Should stop when paused."""
        mock_voice_client.is_playing.return_value = False
        mock_voice_client.is_paused.return_value = True

        result = player.stop(mock_voice_client, guild_id=123)

        assert result is True
        mock_voice_client.stop.assert_called_once()

    def test_stop_handles_exception(self, player, mock_voice_client):
        """Should handle exceptions during stop."""
        mock_voice_client.is_playing.return_value = True
        mock_voice_client.stop.side_effect = RuntimeError("Stop error")

        result = player.stop(mock_voice_client, guild_id=123)

        assert result is False

    def test_pause_success(self, player, mock_voice_client):
        """Should pause playback successfully."""
        mock_voice_client.is_playing.return_value = True

        result = player.pause(mock_voice_client, guild_id=123)

        assert result is True
        mock_voice_client.pause.assert_called_once()
        assert player.get_state(123) == PlayerState.PAUSED

    def test_pause_when_not_playing(self, player, mock_voice_client):
        """Should return False when not playing."""
        mock_voice_client.is_playing.return_value = False

        result = player.pause(mock_voice_client, guild_id=123)

        assert result is False
        mock_voice_client.pause.assert_not_called()

    def test_pause_handles_exception(self, player, mock_voice_client):
        """Should handle exceptions during pause."""
        mock_voice_client.is_playing.return_value = True
        mock_voice_client.pause.side_effect = RuntimeError("Pause error")

        result = player.pause(mock_voice_client, guild_id=123)

        assert result is False

    def test_resume_success(self, player, mock_voice_client):
        """Should resume playback successfully."""
        mock_voice_client.is_paused.return_value = True

        result = player.resume(mock_voice_client, guild_id=123)

        assert result is True
        mock_voice_client.resume.assert_called_once()
        assert player.get_state(123) == PlayerState.PLAYING

    def test_resume_when_not_paused(self, player, mock_voice_client):
        """Should return False when not paused."""
        mock_voice_client.is_paused.return_value = False

        result = player.resume(mock_voice_client, guild_id=123)

        assert result is False
        mock_voice_client.resume.assert_not_called()

    def test_resume_handles_exception(self, player, mock_voice_client):
        """Should handle exceptions during resume."""
        mock_voice_client.is_paused.return_value = True
        mock_voice_client.resume.side_effect = RuntimeError("Resume error")

        result = player.resume(mock_voice_client, guild_id=123)

        assert result is False


# =============================================================================
# Volume Control Tests
# =============================================================================


class TestVolumeControl:
    """Tests for volume control."""

    def test_set_volume_success(self, player, mock_voice_client):
        """Should set volume successfully."""
        mock_source = MagicMock(spec=discord.PCMVolumeTransformer)
        mock_voice_client.source = mock_source

        result = player.set_volume(mock_voice_client, 0.75)

        assert result is True
        assert mock_source.volume == 0.75

    def test_set_volume_clamps_to_max(self, player, mock_voice_client):
        """Should clamp volume to maximum of 2.0."""
        mock_source = MagicMock(spec=discord.PCMVolumeTransformer)
        mock_voice_client.source = mock_source

        player.set_volume(mock_voice_client, 5.0)

        assert mock_source.volume == 2.0

    def test_set_volume_clamps_to_min(self, player, mock_voice_client):
        """Should clamp volume to minimum of 0.0."""
        mock_source = MagicMock(spec=discord.PCMVolumeTransformer)
        mock_voice_client.source = mock_source

        player.set_volume(mock_voice_client, -1.0)

        assert mock_source.volume == 0.0

    def test_set_volume_wrong_source_type(self, player, mock_voice_client):
        """Should return False for non-PCMVolumeTransformer sources."""
        mock_voice_client.source = MagicMock()  # Not a PCMVolumeTransformer

        result = player.set_volume(mock_voice_client, 0.5)

        assert result is False

    def test_set_volume_handles_exception(self, player, mock_voice_client):
        """Should handle exceptions during volume setting."""
        mock_voice_client.source = None

        result = player.set_volume(mock_voice_client, 0.5)

        assert result is False

    def test_get_volume_success(self, player, mock_voice_client):
        """Should get current volume."""
        mock_source = MagicMock(spec=discord.PCMVolumeTransformer)
        mock_source.volume = 0.6
        mock_voice_client.source = mock_source

        volume = player.get_volume(mock_voice_client)

        assert volume == 0.6

    def test_get_volume_wrong_source_type(self, player, mock_voice_client):
        """Should return None for non-PCMVolumeTransformer sources."""
        mock_voice_client.source = MagicMock()

        volume = player.get_volume(mock_voice_client)

        assert volume is None

    def test_get_volume_handles_exception(self, player, mock_voice_client):
        """Should return None on exception."""
        mock_voice_client.source = None

        volume = player.get_volume(mock_voice_client)

        assert volume is None


# =============================================================================
# State Management Tests
# =============================================================================


class TestStateManagement:
    """Tests for state management."""

    def test_get_state_default_idle(self, player):
        """Should return IDLE for unknown guild."""
        state = player.get_state(999)

        assert state == PlayerState.IDLE

    def test_get_state_returns_current_state(self, player):
        """Should return current state for tracked guild."""
        player._states[123] = PlayerState.PLAYING

        state = player.get_state(123)

        assert state == PlayerState.PLAYING


# =============================================================================
# Cleanup Tests
# =============================================================================


class TestCleanup:
    """Tests for resource cleanup."""

    def test_cleanup_guild_removes_source(self, player):
        """Should clean up audio source."""
        mock_source = MagicMock()
        player._active_sources[123] = mock_source

        player._cleanup_guild(123)

        assert 123 not in player._active_sources
        mock_source.cleanup.assert_called_once()

    def test_cleanup_guild_handles_source_exception(self, player):
        """Should handle exceptions during source cleanup."""
        mock_source = MagicMock()
        mock_source.cleanup.side_effect = RuntimeError("Cleanup error")
        player._active_sources[123] = mock_source

        player._cleanup_guild(123)  # Should not raise

        assert 123 not in player._active_sources

    def test_cleanup_guild_removes_process(self, player):
        """Should clean up FFmpeg process."""
        mock_process = MagicMock()
        player._active_processes[123] = mock_process

        player._cleanup_guild(123)

        assert 123 not in player._active_processes
        mock_process.kill.assert_called_once()

    def test_cleanup_guild_handles_process_exception(self, player):
        """Should handle exceptions during process cleanup."""
        mock_process = MagicMock()
        mock_process.kill.side_effect = RuntimeError("Kill error")
        player._active_processes[123] = mock_process

        player._cleanup_guild(123)  # Should not raise

        assert 123 not in player._active_processes

    def test_cleanup_all(self, player):
        """Should clean up all guilds."""
        player._active_sources[1] = MagicMock()
        player._active_sources[2] = MagicMock()
        player._states[1] = PlayerState.PLAYING
        player._states[2] = PlayerState.PAUSED

        count = player.cleanup_all()

        assert count == 2
        assert len(player._active_sources) == 0
        assert len(player._states) == 0


# =============================================================================
# Error Handler Tests
# =============================================================================


class TestErrorHandler:
    """Tests for error handling."""

    def test_set_error_handler(self, player):
        """Should set error handler callback."""
        handler = MagicMock()

        player.set_error_handler(handler)

        assert player._on_error == handler

    def test_get_active_count(self, player):
        """Should return number of active sessions."""
        player._active_sources[1] = MagicMock()
        player._active_sources[2] = MagicMock()
        player._active_sources[3] = MagicMock()

        count = player.get_active_count()

        assert count == 3
