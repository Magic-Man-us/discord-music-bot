"""Tests for SkipCog — _send_skip_success, _send_skip_failure, and edge cases."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_music_player.domain.shared.messages import DiscordUIMessages
from discord_music_player.domain.voting.value_objects import VoteResult
from discord_music_player.infrastructure.discord.cogs.skip_cog import SkipCog


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_container():
    container = MagicMock()
    container.voice_warmup_tracker = MagicMock()
    container.voice_warmup_tracker.remaining_seconds.return_value = 0
    container.settings = MagicMock()
    container.settings.discord.owner_ids = [999]
    container.playback_service = MagicMock()
    container.playback_service.skip_track = AsyncMock()
    container.vote_skip_handler = MagicMock()
    container.vote_skip_handler.handle = AsyncMock()
    return container


@pytest.fixture
def cog(mock_container):
    bot = MagicMock()
    return SkipCog(bot, mock_container)


@pytest.fixture
def interaction():
    i = MagicMock(spec=discord.Interaction)
    i.response = MagicMock()
    i.response.is_done.return_value = False
    i.response.send_message = AsyncMock()
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
    member.guild_permissions = MagicMock()
    member.guild_permissions.administrator = False
    i.user = member
    return i


def _vote_result(result: VoteResult, action_executed: bool = False) -> MagicMock:
    r = MagicMock()
    r.result = result
    r.votes_current = 2
    r.votes_needed = 3
    r.action_executed = action_executed
    return r


# =============================================================================
# _send_skip_success
# =============================================================================


@pytest.mark.asyncio
async def test_send_skip_success_requester_skip(cog, interaction, mock_container):
    sample_track = MagicMock()
    sample_track.title = "My Track"
    mock_container.playback_service.skip_track = AsyncMock(return_value=sample_track)

    result = _vote_result(VoteResult.REQUESTER_SKIP, action_executed=True)

    await cog._send_skip_success(interaction, result)

    msg = interaction.response.send_message.call_args[0][0]
    assert "Requester skipped" in msg
    assert "My Track" in msg


@pytest.mark.asyncio
async def test_send_skip_success_auto_skip(cog, interaction, mock_container):
    sample_track = MagicMock()
    sample_track.title = "Auto Song"
    mock_container.playback_service.skip_track = AsyncMock(return_value=sample_track)

    result = _vote_result(VoteResult.AUTO_SKIP, action_executed=True)

    await cog._send_skip_success(interaction, result)

    msg = interaction.response.send_message.call_args[0][0]
    assert "Auto-skipped" in msg


@pytest.mark.asyncio
async def test_send_skip_success_threshold_met(cog, interaction, mock_container):
    sample_track = MagicMock()
    sample_track.title = "Voted Song"
    mock_container.playback_service.skip_track = AsyncMock(return_value=sample_track)

    result = _vote_result(VoteResult.THRESHOLD_MET, action_executed=True)

    await cog._send_skip_success(interaction, result)

    msg = interaction.response.send_message.call_args[0][0]
    assert "threshold" in msg.lower() or "Skipped" in msg


@pytest.mark.asyncio
async def test_send_skip_success_default_case(cog, interaction, mock_container):
    sample_track = MagicMock()
    sample_track.title = "Unknown Song"
    mock_container.playback_service.skip_track = AsyncMock(return_value=sample_track)

    # Use an unusual result that doesn't match specific cases
    result = _vote_result(VoteResult.VOTE_RECORDED, action_executed=True)

    await cog._send_skip_success(interaction, result)

    msg = interaction.response.send_message.call_args[0][0]
    assert "Skipped" in msg


# =============================================================================
# _send_skip_failure
# =============================================================================


@pytest.mark.asyncio
async def test_send_skip_failure_no_playing(cog, interaction):
    result = _vote_result(VoteResult.NO_PLAYING)

    await cog._send_skip_failure(interaction, result)

    msg = interaction.response.send_message.call_args[0][0]
    assert msg == DiscordUIMessages.STATE_NOTHING_PLAYING


@pytest.mark.asyncio
async def test_send_skip_failure_not_in_channel(cog, interaction):
    result = _vote_result(VoteResult.NOT_IN_CHANNEL)

    await cog._send_skip_failure(interaction, result)

    msg = interaction.response.send_message.call_args[0][0]
    assert msg == DiscordUIMessages.VOTE_NOT_IN_CHANNEL


@pytest.mark.asyncio
async def test_send_skip_failure_already_voted(cog, interaction):
    result = _vote_result(VoteResult.ALREADY_VOTED)

    await cog._send_skip_failure(interaction, result)

    msg = interaction.response.send_message.call_args[0][0]
    assert "already voted" in msg.lower()


@pytest.mark.asyncio
async def test_send_skip_failure_vote_recorded(cog, interaction):
    result = _vote_result(VoteResult.VOTE_RECORDED)

    await cog._send_skip_failure(interaction, result)

    msg = interaction.response.send_message.call_args[0][0]
    assert "2" in msg and "3" in msg  # votes_current/votes_needed


@pytest.mark.asyncio
async def test_send_skip_failure_default(cog, interaction):
    result = _vote_result(VoteResult.INVALID_VOTE)

    await cog._send_skip_failure(interaction, result)

    msg = interaction.response.send_message.call_args[0][0]
    assert msg == DiscordUIMessages.VOTE_SKIP_PROCESSED


# =============================================================================
# User not a Member
# =============================================================================


@pytest.mark.asyncio
async def test_skip_user_not_member(cog, interaction, mock_container):
    # Pass voice guard but then fail the isinstance check
    mock_container.vote_skip_handler.handle = AsyncMock()

    # User is Member for the voice guard, but we set it to a non-Member after
    interaction.user = MagicMock(spec=discord.User)
    interaction.user.voice = None

    await cog.skip.callback(cog, interaction, force=False)

    # Should be rejected by voice guard (user not in voice)
    interaction.response.send_message.assert_called_once()


# =============================================================================
# setup()
# =============================================================================


@pytest.mark.asyncio
async def test_setup_no_container():
    from discord_music_player.infrastructure.discord.cogs.skip_cog import setup

    bot = MagicMock()
    del bot.container

    with pytest.raises(RuntimeError):
        await setup(bot)
