"""Tests for QueueCog — shuffle_history and uncovered branches."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_music_player.domain.shared.messages import DiscordUIMessages
from discord_music_player.infrastructure.discord.cogs.queue_cog import QueueCog


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_container():
    container = MagicMock()
    container.voice_warmup_tracker = MagicMock()
    container.voice_warmup_tracker.remaining_seconds.return_value = 0

    container.voice_adapter = MagicMock()
    container.voice_adapter.is_connected = MagicMock(return_value=True)
    container.voice_adapter.ensure_connected = AsyncMock(return_value=True)

    container.queue_service = MagicMock()
    container.queue_service.enqueue = AsyncMock()
    container.queue_service.get_queue = AsyncMock()
    container.queue_service.shuffle = AsyncMock()
    container.queue_service.remove = AsyncMock()
    container.queue_service.clear = AsyncMock()
    container.queue_service.toggle_loop = AsyncMock()

    container.playback_service = MagicMock()
    container.playback_service.start_playback = AsyncMock()

    container.history_repository = MagicMock()
    container.history_repository.get_recent = AsyncMock()

    container.message_state_manager = MagicMock()
    container.message_state_manager.reset = MagicMock()

    return container


@pytest.fixture
def cog(mock_container):
    bot = MagicMock()
    return QueueCog(bot, mock_container)


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


def _track(track_id: str = "t1") -> MagicMock:
    t = MagicMock()
    t.id = MagicMock()
    t.id.value = track_id
    t.title = f"Track {track_id}"
    t.duration_seconds = 180
    t.requested_by_id = 222
    t.requested_by_name = "TestUser"
    return t


# =============================================================================
# shuffle_history
# =============================================================================


@pytest.mark.asyncio
async def test_shuffle_history_success(cog, interaction, mock_container):
    tracks = [_track("t1"), _track("t2"), _track("t3")]
    mock_container.history_repository.get_recent = AsyncMock(return_value=tracks)

    enqueue_result = MagicMock()
    enqueue_result.success = True
    enqueue_result.should_start = True
    mock_container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

    with patch("random.shuffle"):
        await cog.shuffle_history.callback(cog, interaction, limit=100)

    assert mock_container.queue_service.enqueue.await_count == 3
    mock_container.playback_service.start_playback.assert_awaited_once_with(111)
    msg = interaction.followup.send.call_args[0][0]
    assert "3" in msg


@pytest.mark.asyncio
async def test_shuffle_history_no_history(cog, interaction, mock_container):
    mock_container.history_repository.get_recent = AsyncMock(return_value=[])

    await cog.shuffle_history.callback(cog, interaction, limit=100)

    msg = interaction.followup.send.call_args[0][0]
    assert msg == DiscordUIMessages.STATE_NO_TRACKS_PLAYED_YET


@pytest.mark.asyncio
async def test_shuffle_history_deduplicates(cog, interaction, mock_container):
    # Same track_id appears 3 times
    tracks = [_track("t1"), _track("t1"), _track("t1")]
    mock_container.history_repository.get_recent = AsyncMock(return_value=tracks)

    enqueue_result = MagicMock()
    enqueue_result.success = True
    enqueue_result.should_start = False
    mock_container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

    await cog.shuffle_history.callback(cog, interaction, limit=100)

    # Only 1 unique track, so enqueue called once
    assert mock_container.queue_service.enqueue.await_count == 1
    msg = interaction.followup.send.call_args[0][0]
    assert "1" in msg


# =============================================================================
# queue with total_duration
# =============================================================================


@pytest.mark.asyncio
async def test_queue_with_total_duration_shows_footer(cog, interaction, mock_container):
    track = _track("t1")
    queue_info = MagicMock()
    queue_info.total_tracks = 1
    queue_info.current_track = None
    queue_info.tracks = [track]
    queue_info.total_duration = 360
    mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

    await cog.queue.callback(cog, interaction, page=1)

    call_args = interaction.response.send_message.call_args
    embed = call_args[1]["embed"]
    assert embed.footer is not None
    assert "Total duration" in embed.footer.text


@pytest.mark.asyncio
async def test_queue_without_total_duration_no_footer(cog, interaction, mock_container):
    track = _track("t1")
    queue_info = MagicMock()
    queue_info.total_tracks = 1
    queue_info.current_track = None
    queue_info.tracks = [track]
    queue_info.total_duration = None
    mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

    await cog.queue.callback(cog, interaction, page=1)

    call_args = interaction.response.send_message.call_args
    embed = call_args[1]["embed"]
    assert embed.footer.text is discord.utils.MISSING or embed.footer is None or "Total duration" not in str(embed.footer)


# =============================================================================
# setup()
# =============================================================================


@pytest.mark.asyncio
async def test_setup_no_container():
    from discord_music_player.infrastructure.discord.cogs.queue_cog import setup

    bot = MagicMock()
    del bot.container

    with pytest.raises(RuntimeError):
        await setup(bot)
