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
    member.bot = False
    other = MagicMock(spec=discord.Member)
    other.bot = False
    member.voice.channel.members = [member, other]
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

    await cog.radio.callback(cog, interaction, action=_choice("off"), query=None)

    mock_container.radio_service.disable_radio.assert_called_once_with(111)
    mock_container.queue_service.clear_recommendations.assert_awaited_once_with(111)
    msg = interaction.followup.send.call_args[0][0]
    assert "3" in msg
    assert "Removed" in msg


@pytest.mark.asyncio
async def test_clear_zero_recommendations(cog, interaction, mock_container):
    mock_container.queue_service.clear_recommendations = AsyncMock(return_value=0)

    await cog.radio.callback(cog, interaction, action=_choice("off"), query=None)

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

    await cog.radio.callback(cog, interaction, action=None, count=3, query=None)

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

    await cog.radio.callback(cog, interaction, action=None, count=3, query=None)

    call_kwargs = interaction.followup.send.call_args[1]
    assert call_kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_toggle_disable_with_message(cog, interaction, mock_container):
    result = MagicMock()
    result.enabled = False
    result.message = "No current track"
    mock_container.radio_service.toggle_radio = AsyncMock(return_value=result)

    await cog.radio.callback(cog, interaction, action=None, count=3, query=None)

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

    await cog.radio.callback(cog, interaction, action=None, count=3, query="my query")

    mock_container.audio_resolver.resolve.assert_awaited_once_with("my query")
    mock_container.queue_service.enqueue.assert_awaited_once()
    mock_container.playback_service.start_playback.assert_awaited_once_with(111)


@pytest.mark.asyncio
async def test_toggle_with_query_resolve_fails(cog, interaction, mock_container):
    """When audio_resolver returns None, sends ephemeral error and stops."""
    mock_container.audio_resolver.resolve = AsyncMock(return_value=None)

    await cog.radio.callback(cog, interaction, action=None, count=3, query="bad query")

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

    await cog.radio.callback(cog, interaction, action=None, count=3, query="dup query")

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

    await cog.radio.callback(cog, interaction, action=None, count=3, query="new seed")

    mock_container.radio_service.disable_radio.assert_called_once_with(111)


# =============================================================================
# Guard: voice check fails
# =============================================================================


@pytest.mark.asyncio
async def test_voice_check_fails_returns_early(cog, interaction, mock_container):
    interaction.user.voice = None

    await cog.radio.callback(cog, interaction, action=None, count=3, query=None)

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


# =============================================================================
# cog_load / cog_unload — subscribe/unsubscribe to RadioPoolExhausted
# =============================================================================


@pytest.mark.asyncio
async def test_cog_load_subscribes_once(cog):
    from discord_music_player.domain.shared.events import reset_event_bus

    reset_event_bus()
    cog._bus = MagicMock()
    cog._subscribed = False

    await cog.cog_load()
    assert cog._subscribed is True
    cog._bus.subscribe.assert_called_once()

    cog._bus.subscribe.reset_mock()
    await cog.cog_load()
    cog._bus.subscribe.assert_not_called()


@pytest.mark.asyncio
async def test_cog_unload_unsubscribes_once(cog):
    cog._bus = MagicMock()
    cog._subscribed = True

    await cog.cog_unload()
    assert cog._subscribed is False
    cog._bus.unsubscribe.assert_called_once()

    cog._bus.unsubscribe.reset_mock()
    await cog.cog_unload()
    cog._bus.unsubscribe.assert_not_called()


# =============================================================================
# _on_pool_exhausted
# =============================================================================


@pytest.mark.asyncio
async def test_on_pool_exhausted_warns_when_no_channel_id(cog):
    from discord_music_player.domain.shared.events import RadioPoolExhausted

    event = RadioPoolExhausted(guild_id=1, channel_id=None, tracks_generated=5)
    cog.logger = MagicMock()
    await cog._on_pool_exhausted(event)
    cog.logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_on_pool_exhausted_returns_when_channel_missing(cog):
    from discord_music_player.domain.shared.events import RadioPoolExhausted

    cog.bot.get_channel = MagicMock(return_value=None)
    event = RadioPoolExhausted(guild_id=1, channel_id=42, tracks_generated=5)
    await cog._on_pool_exhausted(event)


@pytest.mark.asyncio
async def test_on_pool_exhausted_returns_when_channel_not_messageable(cog):
    from discord_music_player.domain.shared.events import RadioPoolExhausted

    cog.bot.get_channel = MagicMock(return_value=object())
    event = RadioPoolExhausted(guild_id=1, channel_id=42, tracks_generated=5)
    await cog._on_pool_exhausted(event)


@pytest.mark.asyncio
async def test_on_pool_exhausted_sends_continue_prompt(cog, mock_container):
    from discord_music_player.domain.shared.events import RadioPoolExhausted

    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock(return_value=MagicMock())
    cog.bot.get_channel = MagicMock(return_value=channel)

    state = MagicMock()
    state.tracks_consumed = 7
    mock_container.radio_service.get_state = MagicMock(return_value=state)

    event = RadioPoolExhausted(guild_id=1, channel_id=42, tracks_generated=5)
    await cog._on_pool_exhausted(event)

    channel.send.assert_awaited_once()
    kwargs = channel.send.call_args.kwargs
    assert "embed" in kwargs and "view" in kwargs


@pytest.mark.asyncio
async def test_on_pool_exhausted_falls_back_to_event_count_when_no_state(
    cog, mock_container
):
    from discord_music_player.domain.shared.events import RadioPoolExhausted

    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock(return_value=MagicMock())
    cog.bot.get_channel = MagicMock(return_value=channel)
    mock_container.radio_service.get_state = MagicMock(return_value=None)

    event = RadioPoolExhausted(guild_id=1, channel_id=42, tracks_generated=11)
    await cog._on_pool_exhausted(event)

    channel.send.assert_awaited_once()


# =============================================================================
# /radio without count -> _show_count_select branch
# =============================================================================


@pytest.mark.asyncio
async def test_radio_without_count_shows_count_select(cog, interaction):
    interaction.response.send_message = AsyncMock(
        return_value=MagicMock(spec=discord.InteractionMessage)
    )
    await cog.radio.callback(cog, interaction, action=None, count=None, query=None)
    interaction.response.send_message.assert_awaited_once()
    kwargs = interaction.response.send_message.call_args.kwargs
    assert kwargs.get("ephemeral") is True
    assert "view" in kwargs


# =============================================================================
# _seed_track voice-guard rejection
# =============================================================================


@pytest.mark.asyncio
async def test_seed_track_returns_false_when_voice_guard_fails(cog, mock_container):
    i = MagicMock(spec=discord.Interaction)
    i.guild = MagicMock()
    i.guild.id = 1
    # User is a non-Member (e.g. DM) -> ensure_voice rejects
    i.user = MagicMock(spec=discord.User)
    i.response = MagicMock()
    i.response.is_done = MagicMock(return_value=False)
    i.response.send_message = AsyncMock()
    i.followup = MagicMock()
    i.followup.send = AsyncMock()

    result = await cog._seed_track(i, "some query")
    assert result is False
    mock_container.audio_resolver.resolve.assert_not_awaited()
