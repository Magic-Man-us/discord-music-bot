"""Tests for check_user_in_voice guard and cog setup() functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_music_player.domain.shared.messages import DiscordUIMessages
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    check_user_in_voice,
)


def _make_interaction(
    *,
    user_is_member: bool = True,
    in_voice: bool = True,
    user_channel_id: int = 100,
    bot_channel_id: int | None = 100,
    guild_id: int = 1,
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    if user_is_member:
        user = MagicMock(spec=discord.Member)
        if in_voice:
            user.voice = MagicMock()
            user.voice.channel = MagicMock()
            user.voice.channel.id = user_channel_id
        else:
            user.voice = None
    else:
        user = MagicMock(spec=discord.User)

    interaction.user = user

    # Build guild / voice_client mock
    guild = MagicMock()
    if bot_channel_id is not None:
        guild.voice_client = MagicMock()
        guild.voice_client.channel = MagicMock()
        guild.voice_client.channel.id = bot_channel_id
    else:
        guild.voice_client = None

    interaction.client = MagicMock()
    interaction.client.get_guild = MagicMock(return_value=guild)

    return interaction


# =============================================================================
# check_user_in_voice tests
# =============================================================================


@pytest.mark.asyncio
async def test_user_not_member_rejects():
    interaction = _make_interaction(user_is_member=False)

    result = await check_user_in_voice(interaction, guild_id=1)

    assert result is False
    interaction.response.send_message.assert_awaited_once()
    msg = interaction.response.send_message.call_args[0][0]
    assert msg == DiscordUIMessages.STATE_VERIFY_VOICE_FAILED


@pytest.mark.asyncio
async def test_user_not_in_voice_rejects():
    interaction = _make_interaction(in_voice=False)

    result = await check_user_in_voice(interaction, guild_id=1)

    assert result is False
    msg = interaction.response.send_message.call_args[0][0]
    assert msg == DiscordUIMessages.STATE_NEED_TO_BE_IN_VOICE


@pytest.mark.asyncio
async def test_user_in_different_channel_rejects():
    interaction = _make_interaction(user_channel_id=100, bot_channel_id=200)

    result = await check_user_in_voice(interaction, guild_id=1)

    assert result is False
    msg = interaction.response.send_message.call_args[0][0]
    assert msg == DiscordUIMessages.STATE_MUST_BE_IN_VOICE


@pytest.mark.asyncio
async def test_user_in_same_channel_passes():
    interaction = _make_interaction(user_channel_id=100, bot_channel_id=100)

    result = await check_user_in_voice(interaction, guild_id=1)

    assert result is True


@pytest.mark.asyncio
async def test_bot_not_connected_passes():
    interaction = _make_interaction(bot_channel_id=None)

    result = await check_user_in_voice(interaction, guild_id=1)

    assert result is True


# =============================================================================
# setup() functions — missing container raises RuntimeError
# =============================================================================


@pytest.mark.asyncio
async def test_skip_cog_setup_no_container():
    from discord_music_player.infrastructure.discord.cogs.skip_cog import setup

    bot = MagicMock()
    bot.container = None  # getattr fallback
    del bot.container  # make getattr return None

    with pytest.raises(RuntimeError):
        await setup(bot)


@pytest.mark.asyncio
async def test_queue_cog_setup_no_container():
    from discord_music_player.infrastructure.discord.cogs.queue_cog import setup

    bot = MagicMock()
    del bot.container

    with pytest.raises(RuntimeError):
        await setup(bot)


@pytest.mark.asyncio
async def test_radio_cog_setup_no_container():
    from discord_music_player.infrastructure.discord.cogs.radio_cog import setup

    bot = MagicMock()
    del bot.container

    with pytest.raises(RuntimeError):
        await setup(bot)


@pytest.mark.asyncio
async def test_now_playing_cog_setup_no_container():
    from discord_music_player.infrastructure.discord.cogs.now_playing_cog import setup

    bot = MagicMock()
    del bot.container

    with pytest.raises(RuntimeError):
        await setup(bot)
