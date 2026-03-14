"""Tests for RadioCog — /radio command with toggle and clear actions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

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

    # Audio/playback services for _seed_track
    container.audio_resolver = MagicMock()
    container.audio_resolver.resolve = AsyncMock(return_value=None)

    container.voice_adapter = MagicMock()
    container.voice_adapter.is_connected = MagicMock(return_value=True)

    container.playback_service = MagicMock()
    container.playback_service.start_playback = AsyncMock()

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
    track_mock = MagicMock()
    track_mock.title = "Next Track"

    result = MagicMock()
    result.enabled = True
    result.seed_title = "Cool Song"
    result.tracks_added = 2
    result.generated_tracks = [track_mock, track_mock]
    mock_container.radio_service.toggle_radio = AsyncMock(return_value=result)

    queue_info = MagicMock()
    queue_info.total_tracks = 2
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
# Toggle with query — seeds via container services (no cross-cog coupling)
# =============================================================================


@pytest.mark.asyncio
async def test_toggle_with_query_resolves_and_enqueues(cog, interaction, mock_container):
    """Seed query resolves a track via audio_resolver and enqueues it."""
    seed_track = MagicMock()
    seed_track.title = "Queried Song"
    mock_container.audio_resolver.resolve = AsyncMock(return_value=seed_track)

    enqueue_result = MagicMock()
    enqueue_result.success = True
    enqueue_result.should_start = True
    mock_container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

    radio_result = MagicMock()
    radio_result.enabled = True
    radio_result.seed_title = "Queried Song"
    radio_result.generated_tracks = [seed_track]
    mock_container.radio_service.toggle_radio = AsyncMock(return_value=radio_result)

    queue_info = MagicMock()
    queue_info.total_tracks = 1
    mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

    await cog.radio.callback(cog, interaction, query="my query", action=None)

    mock_container.audio_resolver.resolve.assert_awaited_once_with("my query")
    mock_container.queue_service.enqueue.assert_awaited_once()
    mock_container.playback_service.start_playback.assert_awaited_once_with(111)


@pytest.mark.asyncio
async def test_toggle_with_query_resolve_fails(cog, interaction, mock_container):
    """When audio_resolver returns None, sends ephemeral error and stops."""
    mock_container.audio_resolver.resolve = AsyncMock(return_value=None)

    await cog.radio.callback(cog, interaction, query="bad query", action=None)

    msg = interaction.followup.send.call_args[0][0]
    assert "Couldn't find" in msg
    mock_container.radio_service.toggle_radio.assert_not_awaited()


@pytest.mark.asyncio
async def test_toggle_with_query_enqueue_fails(cog, interaction, mock_container):
    """When enqueue returns failure, sends the error message and stops."""
    seed_track = MagicMock()
    seed_track.title = "Dup Song"
    mock_container.audio_resolver.resolve = AsyncMock(return_value=seed_track)

    enqueue_result = MagicMock()
    enqueue_result.success = False
    enqueue_result.message = "Already in queue"
    mock_container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

    await cog.radio.callback(cog, interaction, query="dup query", action=None)

    msg = interaction.followup.send.call_args[0][0]
    assert "Already in queue" in msg
    mock_container.radio_service.toggle_radio.assert_not_awaited()


@pytest.mark.asyncio
async def test_toggle_with_query_disables_existing_radio(cog, interaction, mock_container):
    """When radio is already enabled, _seed_track disables it so toggle re-enables fresh."""
    mock_container.radio_service.is_enabled = MagicMock(return_value=True)

    seed_track = MagicMock()
    seed_track.title = "New Seed"
    mock_container.audio_resolver.resolve = AsyncMock(return_value=seed_track)

    enqueue_result = MagicMock()
    enqueue_result.success = True
    enqueue_result.should_start = False
    mock_container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

    radio_result = MagicMock()
    radio_result.enabled = True
    radio_result.seed_title = "New Seed"
    radio_result.generated_tracks = [seed_track]
    mock_container.radio_service.toggle_radio = AsyncMock(return_value=radio_result)

    queue_info = MagicMock()
    queue_info.total_tracks = 1
    mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

    await cog.radio.callback(cog, interaction, query="new seed", action=None)

    mock_container.radio_service.disable_radio.assert_called_once_with(111)


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
