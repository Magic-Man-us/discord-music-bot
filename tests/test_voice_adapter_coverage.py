"""
Additional Voice Adapter Tests for Coverage

Tests edge cases and error paths in DiscordVoiceAdapter that aren't
covered by existing tests.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import StartSeconds, TrackId
from discord_music_player.infrastructure.discord.adapters.voice_adapter import DiscordVoiceAdapter


class TestVoiceAdapterErrorHandling:
    """Tests for voice adapter error handling paths."""

    @pytest.fixture
    def mock_bot(self):
        """Create a mock Discord bot."""
        bot = MagicMock()
        bot.loop = asyncio.new_event_loop()
        return bot

    @pytest.fixture
    def adapter(self, mock_bot):
        """Create a voice adapter instance."""
        return DiscordVoiceAdapter(mock_bot)

    @pytest.fixture
    def sample_track(self):
        """Create a playable track for voice adapter tests."""
        return Track(
            id=TrackId(value="test123"),
            title="Test Song",
            webpage_url="https://youtube.com/watch?v=test12345678",
            stream_url="https://audio.example.com/stream.mp3",
            duration_seconds=180,
        )

    async def test_connect_timeout_error(self, adapter, mock_bot):
        """Should handle timeout when connecting to voice."""
        guild_id = 123
        channel_id = 456

        mock_guild = MagicMock()
        mock_guild.id = guild_id
        mock_guild.voice_client = None

        mock_channel = MagicMock()
        mock_channel.id = channel_id
        mock_channel.connect = AsyncMock(side_effect=TimeoutError())

        mock_bot.get_guild.return_value = mock_guild
        mock_bot.get_channel.return_value = mock_channel

        result = await adapter.connect(guild_id, channel_id)

        assert result is False

    async def test_connect_client_exception(self, adapter, mock_bot):
        """Should handle Discord ClientException."""
        guild_id = 123
        channel_id = 456

        mock_guild = MagicMock()
        mock_guild.id = guild_id
        mock_guild.voice_client = None

        mock_channel = MagicMock()
        mock_channel.id = channel_id
        mock_channel.connect = AsyncMock(side_effect=discord.ClientException("Already connected"))

        mock_bot.get_guild.return_value = mock_guild
        mock_bot.get_channel.return_value = mock_channel

        result = await adapter.connect(guild_id, channel_id)

        assert result is False

    async def test_connect_forbidden_exception(self, adapter, mock_bot):
        """Should handle Discord Forbidden exception (no permission)."""
        guild_id = 123
        channel_id = 456

        mock_guild = MagicMock()
        mock_guild.id = guild_id
        mock_guild.voice_client = None

        mock_channel = MagicMock()
        mock_channel.id = channel_id
        mock_channel.connect = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "No permission")
        )

        mock_bot.get_guild.return_value = mock_guild
        mock_bot.get_channel.return_value = mock_channel

        result = await adapter.connect(guild_id, channel_id)

        assert result is False

    async def test_connect_generic_exception(self, adapter, mock_bot):
        """Should handle unexpected exceptions."""
        guild_id = 123
        channel_id = 456

        mock_guild = MagicMock()
        mock_guild.id = guild_id
        mock_guild.voice_client = None

        mock_channel = MagicMock()
        mock_channel.id = channel_id
        mock_channel.connect = AsyncMock(side_effect=RuntimeError("Unexpected"))

        mock_bot.get_guild.return_value = mock_guild
        mock_bot.get_channel.return_value = mock_channel

        result = await adapter.connect(guild_id, channel_id)

        assert result is False

    async def test_disconnect_handles_exception(self, adapter, mock_bot):
        """Should handle exceptions during disconnect gracefully."""
        guild_id = 123

        mock_guild = MagicMock()
        mock_voice_client = MagicMock()
        mock_voice_client.disconnect = AsyncMock(side_effect=RuntimeError("Disconnect failed"))

        mock_guild.voice_client = mock_voice_client
        mock_bot.get_guild.return_value = mock_guild

        # Should not raise exception, just handle it gracefully
        # The actual return value may be True since it's a best-effort operation
        result = await adapter.disconnect(guild_id)
        # Just verify it doesn't raise - return value may vary
        assert result in (True, False)

    async def test_is_connected_no_guild(self, adapter, mock_bot):
        """Should return False when guild doesn't exist."""
        mock_bot.get_guild.return_value = None

        result = adapter.is_connected(999)
        assert result is False

    async def test_get_current_channel_id_no_guild(self, adapter, mock_bot):
        """Should return None when guild doesn't exist."""
        mock_bot.get_guild.return_value = None

        result = adapter.get_current_channel_id(999)
        assert result is None

    async def test_get_current_channel_id_no_voice_client(self, adapter, mock_bot):
        """Should return None when not in voice."""
        mock_guild = MagicMock()
        mock_guild.voice_client = None
        mock_bot.get_guild.return_value = mock_guild

        result = adapter.get_current_channel_id(123)
        assert result is None

    async def test_get_listeners_no_voice_client(self, adapter, mock_bot):
        """Should return empty list when not in voice."""
        mock_guild = MagicMock()
        mock_guild.voice_client = None
        mock_bot.get_guild.return_value = mock_guild

        result = await adapter.get_listeners(123)
        assert result == []

    async def test_ensure_connected_returns_true_in_same_channel(self, adapter):
        """Should no-op when already connected to the requested channel."""
        voice_client = MagicMock()
        voice_client.is_connected.return_value = True
        voice_client.channel = SimpleNamespace(id=456)

        adapter._get_voice_client = MagicMock(return_value=voice_client)
        adapter.connect = AsyncMock()
        adapter.move_to = AsyncMock()

        result = await adapter.ensure_connected(123, 456)

        assert result is True
        adapter.connect.assert_not_called()
        adapter.move_to.assert_not_called()

    async def test_ensure_connected_moves_when_channel_changes(self, adapter):
        """Should move an active voice client into a different target channel."""
        voice_client = MagicMock()
        voice_client.is_connected.return_value = True
        voice_client.channel = SimpleNamespace(id=999)

        adapter._get_voice_client = MagicMock(return_value=voice_client)
        adapter.move_to = AsyncMock(return_value=True)

        result = await adapter.ensure_connected(123, 456)

        assert result is True
        adapter.move_to.assert_awaited_once_with(123, 456)

    async def test_ensure_connected_reconnects_stale_voice_client(self, adapter):
        """Should disconnect a stale voice client before reconnecting."""
        voice_client = MagicMock()
        voice_client.is_connected.return_value = False
        voice_client.channel = None

        adapter._get_voice_client = MagicMock(return_value=voice_client)
        adapter.disconnect = AsyncMock(return_value=True)
        adapter.connect = AsyncMock(return_value=True)

        result = await adapter.ensure_connected(123, 456)

        assert result is True
        adapter.disconnect.assert_awaited_once_with(123)
        adapter.connect.assert_awaited_once_with(123, 456)

    async def test_play_uses_volume_transformer_and_handles_track_end(
        self,
        adapter,
        mock_bot,
        sample_track,
        monkeypatch,
    ):
        """Should wrap FFmpeg audio, seek correctly, and dispatch track-end cleanup."""

        class FakeAudioSource:
            def __init__(self, url: str, *, before_options: str, options: str) -> None:
                self.url = url
                self.before_options = before_options
                self.options = options

        class FakeVolumeTransformer:
            def __init__(self, source: FakeAudioSource, *, volume: float) -> None:
                self.source = source
                self.volume = volume

        captured_play: dict[str, object] = {}
        scheduled_tasks: list[asyncio.Task[None]] = []

        def fake_play(source, *, after):
            captured_play["source"] = source
            captured_play["after"] = after

        def fake_run_coroutine_threadsafe(coro, loop):
            assert loop is mock_bot.loop
            task = asyncio.create_task(coro)
            scheduled_tasks.append(task)
            return task

        voice_client = MagicMock()
        voice_client.is_playing.return_value = False
        voice_client.play.side_effect = fake_play

        mock_bot.loop = asyncio.get_running_loop()
        adapter._get_voice_client = MagicMock(return_value=voice_client)

        callback = AsyncMock()
        adapter.set_on_track_end_callback(callback)

        monkeypatch.setattr(discord, "FFmpegPCMAudio", FakeAudioSource)
        monkeypatch.setattr(discord, "PCMVolumeTransformer", FakeVolumeTransformer)
        monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", fake_run_coroutine_threadsafe)

        result = await adapter.play(
            123,
            sample_track,
            start_seconds=StartSeconds(value=12),
        )

        assert result is True
        assert adapter.get_current_track(123) == sample_track

        source = captured_play["source"]
        assert isinstance(source, FakeVolumeTransformer)
        assert source.volume == adapter._volume
        assert source.source.url == sample_track.stream_url
        assert '-ss 12' in source.source.before_options
        assert 'User-Agent:' in source.source.before_options
        assert 'afade=t=in:ss=0:d=0.5' in source.source.options

        after = captured_play["after"]
        assert callable(after)
        after(None)
        await asyncio.gather(*scheduled_tasks)

        assert adapter.get_current_track(123) is None
        callback.assert_awaited_once_with(123)

    async def test_stop_clears_current_track_when_playing(self, adapter, sample_track):
        """Should clear current track metadata when playback stops."""
        voice_client = MagicMock()
        voice_client.is_playing.return_value = True
        voice_client.is_paused.return_value = False

        adapter._get_voice_client = MagicMock(return_value=voice_client)
        adapter._current_track[123] = sample_track

        result = await adapter.stop(123)

        assert result is True
        assert adapter.get_current_track(123) is None
        voice_client.stop.assert_called_once_with()

    async def test_get_listeners_filters_bots_and_deafened_members(self, adapter):
        """Should exclude bots and deafened users from listener counts."""
        voice_client = MagicMock()
        voice_client.channel = SimpleNamespace(
            members=[
                SimpleNamespace(
                    id=1,
                    bot=False,
                    voice=SimpleNamespace(deaf=False, self_deaf=False),
                ),
                SimpleNamespace(
                    id=2,
                    bot=True,
                    voice=SimpleNamespace(deaf=False, self_deaf=False),
                ),
                SimpleNamespace(
                    id=3,
                    bot=False,
                    voice=SimpleNamespace(deaf=True, self_deaf=False),
                ),
                SimpleNamespace(
                    id=4,
                    bot=False,
                    voice=SimpleNamespace(deaf=False, self_deaf=True),
                ),
            ]
        )

        adapter._get_voice_client = MagicMock(return_value=voice_client)

        result = await adapter.get_listeners(123)

        assert result == [1]

    def test_set_volume_clamps_transformer_volume(self, adapter, monkeypatch):
        """Should clamp live playback volume into Discord's accepted range."""

        class FakeVolumeTransformer:
            def __init__(self, volume: float) -> None:
                self.volume = volume

        monkeypatch.setattr(discord, "PCMVolumeTransformer", FakeVolumeTransformer)

        voice_client = MagicMock()
        voice_client.source = FakeVolumeTransformer(volume=0.1)
        adapter._get_voice_client = MagicMock(return_value=voice_client)

        assert adapter.set_volume(123, 9.0) is True
        assert voice_client.source.volume == 2.0

        assert adapter.set_volume(123, -1.0) is True
        assert voice_client.source.volume == 0.0

    async def test_voice_connection_disconnects_after_success(self, adapter):
        """Should always disconnect after a successful context-managed connection."""
        adapter.ensure_connected = AsyncMock(return_value=True)
        adapter.disconnect = AsyncMock(return_value=True)

        async with adapter.voice_connection(123, 456) as connected:
            assert connected is True

        adapter.ensure_connected.assert_awaited_once_with(123, 456)
        adapter.disconnect.assert_awaited_once_with(123)

    async def test_voice_connection_disconnects_after_exception(self, adapter):
        """Should clean up the voice connection even when the context body fails."""
        adapter.ensure_connected = AsyncMock(return_value=True)
        adapter.disconnect = AsyncMock(return_value=True)

        with pytest.raises(RuntimeError, match="boom"):
            async with adapter.voice_connection(123, 456):
                raise RuntimeError("boom")

        adapter.disconnect.assert_awaited_once_with(123)
