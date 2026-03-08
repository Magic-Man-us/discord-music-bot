"""Tests for SkipCog — vote skip, force skip, and edge cases."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_music_player.application.commands.vote_skip import VoteSkipResult
from discord_music_player.domain.voting.enums import VoteResult, VoteType
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


# =============================================================================
# VoteSkipResult.format_display — no match/case, uses get_message dispatch
# =============================================================================


@pytest.mark.parametrize(
    "vote_result, expected_fragment",
    [
        (VoteResult.REQUESTER_SKIP, "Requester skipped"),
        (VoteResult.AUTO_SKIP, "Auto-skipped"),
        (VoteResult.THRESHOLD_MET, "threshold met"),
    ],
)
def test_format_display_includes_track_title(vote_result: VoteResult, expected_fragment: str):
    result = VoteSkipResult.from_vote_result(vote_result, votes_current=2, votes_needed=3)
    msg = result.format_display("My Track")
    assert expected_fragment.lower() in msg.lower()
    assert "My Track" in msg


def test_format_display_failure_uses_message():
    result = VoteSkipResult.from_vote_result(VoteResult.NO_PLAYING)
    msg = result.format_display("Irrelevant")
    assert "Nothing is playing" in msg


# =============================================================================
# VoteResult.get_message — domain message dispatch
# =============================================================================


def test_get_message_with_track_title():
    msg = VoteResult.REQUESTER_SKIP.get_message(VoteType.SKIP, track_title="Cool Song")
    assert "Cool Song" in msg


def test_get_message_without_track_title():
    msg = VoteResult.REQUESTER_SKIP.get_message(VoteType.SKIP)
    assert "skipped" in msg.lower()


def test_get_message_failure_no_track():
    msg = VoteResult.NO_PLAYING.get_message(VoteType.SKIP)
    assert "Nothing is playing" in msg


def test_get_message_vote_recorded_shows_counts():
    msg = VoteResult.VOTE_RECORDED.get_message(VoteType.SKIP, votes=2, needed=3)
    assert "2/3" in msg


def test_get_message_already_voted_shows_counts():
    msg = VoteResult.ALREADY_VOTED.get_message(VoteType.SKIP, votes=2, needed=3)
    assert "2/3" in msg


# =============================================================================
# _handle_vote_skip integration (action_executed path)
# =============================================================================


@pytest.mark.asyncio
async def test_handle_vote_skip_action_executed(cog, interaction, mock_container):
    sample_track = MagicMock()
    sample_track.title = "My Track"
    mock_container.playback_service.skip_track = AsyncMock(return_value=sample_track)

    result = VoteSkipResult.from_vote_result(VoteResult.REQUESTER_SKIP)
    mock_container.vote_skip_handler.handle = AsyncMock(return_value=result)

    await cog._handle_vote_skip(interaction, interaction.user)

    mock_container.playback_service.skip_track.assert_awaited_once_with(111)
    msg = interaction.response.send_message.call_args[0][0]
    assert "Requester skipped" in msg
    assert "My Track" in msg


@pytest.mark.asyncio
async def test_handle_vote_skip_no_action(cog, interaction, mock_container):
    result = VoteSkipResult.from_vote_result(VoteResult.VOTE_RECORDED, votes_current=2, votes_needed=3)
    mock_container.vote_skip_handler.handle = AsyncMock(return_value=result)

    await cog._handle_vote_skip(interaction, interaction.user)

    mock_container.playback_service.skip_track.assert_not_awaited()
    msg = interaction.response.send_message.call_args[0][0]
    assert "2/3" in msg


@pytest.mark.asyncio
async def test_handle_vote_skip_nothing_playing(cog, interaction, mock_container):
    result = VoteSkipResult.from_vote_result(VoteResult.NO_PLAYING)
    mock_container.vote_skip_handler.handle = AsyncMock(return_value=result)

    await cog._handle_vote_skip(interaction, interaction.user)

    msg = interaction.response.send_message.call_args[0][0]
    assert "Nothing is playing" in msg


# =============================================================================
# User not a Member
# =============================================================================


@pytest.mark.asyncio
async def test_skip_user_not_member(cog, interaction, mock_container):
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
