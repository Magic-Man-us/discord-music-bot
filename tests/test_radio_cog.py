"""Tests for RadioCog — /radio command with toggle and clear actions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_music_player.infrastructure.discord.cogs.radio_cog import RadioCog


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_container():
    container = MagicMock()
    container.voice_warmup_tracker = MagicMock()
    container.voice_warmup_tracker.remaining_seconds.return_value = 0

    container.radio_service = MagicMock()
    container.radio_service.disable_radio = MagicMock()
    container.radio_service.is_enabled = MagicMock(return_value=False)
    container.radio_service.toggle_radio = AsyncMock()

    container.queue_service = MagicMock()
    container.queue_service.clear_recommendations = AsyncMock(return_value=0)
    container.queue_service.get_queue = AsyncMock()

    return container


@pytest.fixture
def cog(mock_container):
    bot = MagicMock()
    return RadioCog(bot, mock_container)


@pytest.fixture
def interaction():
    i = MagicMock(spec=discord.Interaction)
    i.response = MagicMock()
    i.response.is_done.return_value = False
    i.response.send_message = AsyncMock()
    i.response.defer = AsyncMock()
    i.followup = MagicMock()
    i.followup.send = AsyncMock()

    i.guild = MagicMock()
    i.guild.id = 111

    member = MagicMock(spec=discord.Member)
    member.id = 222
    member.display_name = "TestUser"
    member.name = "testuser"
    member.voice = MagicMock()
    member.voice.channel = MagicMock()
    member.voice.channel.id = 333
    i.user = member
    return i


def _choice(value: str) -> MagicMock:
    c = MagicMock()
    c.value = value
    return c


# =============================================================================
# action="clear"
# =============================================================================


@pytest.mark.asyncio
async def test_clear_removes_recommendations(cog, interaction, mock_container):
    mock_container.queue_service.clear_recommendations = AsyncMock(return_value=3)

    await cog.radio.callback(cog, interaction, query=None, action=_choice("clear"))

    mock_container.radio_service.disable_radio.assert_called_once_with(111)
    mock_container.queue_service.clear_recommendations.assert_awaited_once_with(111)
    msg = interaction.followup.send.call_args[0][0]
    assert "3" in msg
    assert "Removed" in msg


@pytest.mark.asyncio
async def test_clear_zero_recommendations(cog, interaction, mock_container):
    mock_container.queue_service.clear_recommendations = AsyncMock(return_value=0)

    await cog.radio.callback(cog, interaction, query=None, action=_choice("clear"))

    msg = interaction.followup.send.call_args[0][0]
    assert "No AI recommendations" in msg


# =============================================================================
# Toggle — enable (no query)
# =============================================================================


@pytest.mark.asyncio
async def test_toggle_enable_sends_embed(cog, interaction, mock_container):
    result = MagicMock()
    result.enabled = True
    result.seed_title = "Cool Song"
    result.tracks_added = 2
    mock_container.radio_service.toggle_radio = AsyncMock(return_value=result)

    queue_info = MagicMock()
    track = MagicMock()
    track.title = "Next Track"
    queue_info.tracks = [track, track]
    mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

    await cog.radio.callback(cog, interaction, query=None, action=None)

    call_kwargs = interaction.followup.send.call_args[1]
    assert "embed" in call_kwargs
    assert "view" in call_kwargs
    embed = call_kwargs["embed"]
    assert "Radio Enabled" in embed.title


# =============================================================================
# Toggle — disable (no query)
# =============================================================================


@pytest.mark.asyncio
async def test_toggle_disable_sends_ephemeral(cog, interaction, mock_container):
    result = MagicMock()
    result.enabled = False
    result.message = ""
    mock_container.radio_service.toggle_radio = AsyncMock(return_value=result)

    await cog.radio.callback(cog, interaction, query=None, action=None)

    call_kwargs = interaction.followup.send.call_args[1]
    assert call_kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_toggle_disable_with_message(cog, interaction, mock_container):
    result = MagicMock()
    result.enabled = False
    result.message = "No current track"
    mock_container.radio_service.toggle_radio = AsyncMock(return_value=result)

    await cog.radio.callback(cog, interaction, query=None, action=None)

    msg = interaction.followup.send.call_args[0][0]
    assert "No current track" in msg


# =============================================================================
# Toggle with query — seeds radio
# =============================================================================


@pytest.mark.asyncio
async def test_toggle_with_query_calls_execute_play(cog, interaction, mock_container):
    playback_cog_mock = MagicMock()
    playback_cog_mock._execute_play = AsyncMock()
    cog.bot.get_cog = MagicMock(return_value=playback_cog_mock)

    result = MagicMock()
    result.enabled = True
    result.seed_title = "Queried Song"
    result.tracks_added = 1
    mock_container.radio_service.toggle_radio = AsyncMock(return_value=result)

    queue_info = MagicMock()
    queue_info.tracks = []
    mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

    await cog.radio.callback(cog, interaction, query="my query", action=None)

    playback_cog_mock._execute_play.assert_awaited_once_with(interaction, "my query")


@pytest.mark.asyncio
async def test_toggle_with_query_playback_cog_missing(cog, interaction, mock_container):
    cog.bot.get_cog = MagicMock(return_value=None)

    result = MagicMock()
    result.enabled = True
    result.seed_title = "Song"
    result.tracks_added = 0
    mock_container.radio_service.toggle_radio = AsyncMock(return_value=result)

    queue_info = MagicMock()
    queue_info.tracks = []
    mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

    # Should not raise
    await cog.radio.callback(cog, interaction, query="my query", action=None)

    interaction.followup.send.assert_called_once()


# =============================================================================
# Guard: voice check fails
# =============================================================================


@pytest.mark.asyncio
async def test_voice_check_fails_returns_early(cog, interaction, mock_container):
    interaction.user.voice = None

    await cog.radio.callback(cog, interaction, query=None, action=None)

    interaction.response.send_message.assert_called_once()
    interaction.followup.send.assert_not_called()


# =============================================================================
# setup()
# =============================================================================


@pytest.mark.asyncio
async def test_setup_no_container_raises():
    from discord_music_player.infrastructure.discord.cogs.radio_cog import setup

    bot = MagicMock()
    del bot.container

    with pytest.raises(RuntimeError):
        await setup(bot)
