"""Tests for the diagnostics cog activity inspection commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_music_player.infrastructure.discord.cogs.diagnostics_cog import (
    DiagnosticsCog,
    _MemberPresence,
)
from discord_music_player.infrastructure.discord.services.activity_models import ActivityInfo


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock()
    bot.intents = MagicMock()
    bot.intents.presences = True
    return bot


@pytest.fixture
def mock_container():
    """Create a mock DI container."""
    return MagicMock()


@pytest.fixture
def cog(mock_bot, mock_container):
    """Create a diagnostics cog instance."""
    return DiagnosticsCog(mock_bot, mock_container)


@pytest.fixture
def interaction():
    """Create a mock guild interaction."""
    i = MagicMock(spec=discord.Interaction)
    i.response = MagicMock()
    i.response.send_message = AsyncMock()
    i.client = MagicMock()
    i.client.intents = MagicMock()
    i.client.intents.presences = True

    member = MagicMock(spec=discord.Member)
    member.display_name = "TestUser"
    member.activities = []
    i.user = member
    return i


def test_member_presence_render_includes_parser_query_for_generic_spotify():
    member = MagicMock(spec=discord.Member)
    member.display_name = "TestUser"

    spotify = MagicMock(spec=discord.Activity)
    spotify.type = discord.ActivityType.listening
    spotify.application_id = None
    spotify.name = "Spotify"
    spotify.details = "Song Title"
    spotify.state = "Artist Name"

    member.activities = [spotify]

    message = _MemberPresence.from_member(member, presences_enabled=True).render()

    assert "parser query=`Artist Name - Song Title`" in message
    assert "Spotify" in message
    assert "Song Title" in message
    assert "Artist Name" in message


@pytest.mark.parametrize(
    ("spec", "attrs", "expected_kind"),
    [
        (
            discord.Spotify,
            {"title": "T", "artist": "A", "album": "Al", "track_id": "tid"},
            "spotify",
        ),
        (discord.CustomActivity, {"name": "feeling good", "emoji": None}, "custom"),
        (
            discord.Streaming,
            {"name": "stream", "url": "https://twitch.tv/x", "platform": "Twitch"},
            "streaming",
        ),
        (
            discord.Activity,
            {"name": "RPG", "details": "d", "state": "s", "application_id": None},
            "generic",
        ),
        (discord.Game, {}, "unknown"),
    ],
)
def test_from_activity_narrows_to_tagged_detail(spec, attrs, expected_kind):
    act = MagicMock(spec=spec)
    act.type = discord.ActivityType.playing
    for name, value in attrs.items():
        setattr(act, name, value)

    info = ActivityInfo.from_activity(act)

    assert info.detail.kind == expected_kind


def test_member_presence_render_sources_status_from_typed_snapshot():
    member = MagicMock(spec=discord.Member)
    member.display_name = "U"
    member.activities = []
    member.status = "online"
    member.desktop_status = "online"
    member.mobile_status = "idle"
    member.web_status = "offline"

    message = _MemberPresence.from_member(member, presences_enabled=True).render()

    assert "status=`online`" in message
    assert "desktop=`online`" in message
    assert "mobile=`idle`" in message
    assert "web=`offline`" in message


@pytest.mark.asyncio
async def test_diag_activities_sends_ephemeral_activity_dump(cog, interaction):
    spotify = MagicMock(spec=discord.Activity)
    spotify.type = discord.ActivityType.listening
    spotify.application_id = None
    spotify.name = "Spotify"
    spotify.details = "Song Title"
    spotify.state = "Artist Name"
    interaction.user.activities = [spotify]

    await cog.diag_activities.callback(cog, interaction)

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    assert "parser query=`Artist Name - Song Title`" in args[0]
    assert "Spotify" in args[0]
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_diag_activities_reports_no_visible_activity(cog, interaction):
    interaction.user.activities = []

    await cog.diag_activities.callback(cog, interaction)

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    assert "no Discord activities visible" in args[0]
    assert "parser query=`None`" in args[0]
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_diag_activities_compares_interaction_user_with_guild_cache(cog, interaction):
    spotify = MagicMock(spec=discord.Activity)
    spotify.type = discord.ActivityType.listening
    spotify.application_id = None
    spotify.name = "Spotify"
    spotify.details = "Song Title"
    spotify.state = "Artist Name"

    interaction.user.id = 123
    interaction.user.activities = []
    interaction.user.status = "online"
    interaction.user.desktop_status = "online"
    interaction.user.mobile_status = "offline"
    interaction.user.web_status = "offline"
    interaction.guild = MagicMock()

    cached_member = MagicMock(spec=discord.Member)
    cached_member.display_name = "TestUser"
    cached_member.activities = [spotify]
    cached_member.status = "online"
    cached_member.desktop_status = "online"
    cached_member.mobile_status = "offline"
    cached_member.web_status = "offline"
    interaction.guild.get_member.return_value = cached_member

    await cog.diag_activities.callback(cog, interaction)

    args, kwargs = interaction.response.send_message.await_args
    assert "interaction.user" in args[0]
    assert "guild cache" in args[0]
    assert "Artist Name - Song Title" in args[0]
    assert kwargs["ephemeral"] is True
