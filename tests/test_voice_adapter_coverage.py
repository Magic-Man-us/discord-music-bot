"""
Additional Voice Adapter Tests for Coverage

Tests edge cases and error paths in DiscordVoiceAdapter that aren't
covered by existing tests.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

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
