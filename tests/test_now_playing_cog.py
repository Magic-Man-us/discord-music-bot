"""Tests for NowPlayingCog: /current, /played, /user_history."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_music_player.application.services.queue_models import QueueSnapshot
from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.infrastructure.discord.cogs.now_playing_cog import NowPlayingCog

from conftest import (  # noqa: E402  -- pytest adds tests/ to sys.path
    FakeContainer,
    FakeVoiceWarmupTracker,
    make_interaction,
    make_member,
    make_voice_channel,
    make_voice_state,
)


def _track(track_id: str = "abc", **overrides) -> Track:
    base = dict(
        id=TrackId(value=track_id),
        title=overrides.pop("title", f"Title {track_id}"),
        webpage_url=f"https://yt/{track_id}",
        duration_seconds=180,
        artist="A",
        uploader="U",
        like_count=42,
        requested_by_id=999,
        requested_by_name="ReqUser",
        requested_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    base.update(overrides)
    return Track(**base)


def _interaction_in_voice():
    member = make_member(member_id=1)
    member.voice = make_voice_state(channel=make_voice_channel(channel_id=10, members=[member]))
    return member, make_interaction(user=member, guild_id=42)


def _container(*, queue_snapshot=None, recent_tracks=None, recent_by_user=None):
    queue_service = MagicMock()
    queue_service.get_queue = AsyncMock(return_value=queue_snapshot)

    history_repository = MagicMock()
    history_repository.get_recent = AsyncMock(return_value=recent_tracks or [])
    history_repository.get_recent_by_user = AsyncMock(return_value=recent_by_user or [])

    return FakeContainer(
        voice_warmup_tracker=FakeVoiceWarmupTracker(remaining=0),
        queue_service=queue_service,
        history_repository=history_repository,
        ai_enabled=False,
    )


def _make_cog(container) -> NowPlayingCog:
    bot = MagicMock()
    return NowPlayingCog(bot, container)


# =============================================================================
# /current
# =============================================================================


class TestCurrent:
    @pytest.mark.asyncio
    async def test_returns_silently_when_voice_guard_fails(self):
        # User not in voice
        interaction = make_interaction(user=make_member(voice=None), guild_id=42)
        cog = _make_cog(_container())

        await cog.current.callback(cog, interaction)

        # Voice guard sent its own ephemeral; queue_service should never be hit
        cog.container.queue_service.get_queue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_replies_nothing_playing_when_no_current_track(self):
        _, interaction = _interaction_in_voice()
        snapshot = QueueSnapshot(current_track=None, tracks=[], total_tracks=0, total_duration=None)
        cog = _make_cog(_container(queue_snapshot=snapshot))

        await cog.current.callback(cog, interaction)

        # First send call (response) carries the empty-state message
        sent = interaction.response.send_message.call_args
        assert sent.args[0] == "Nothing is playing."
        assert sent.kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_sends_embed_and_view_when_track_playing(self):
        _, interaction = _interaction_in_voice()
        track = _track("cur")
        snapshot = QueueSnapshot(current_track=track, tracks=[_track("nxt")], total_tracks=1, total_duration=180)

        # Original response succeeds
        msg = MagicMock()
        interaction.original_response = AsyncMock(return_value=msg)

        cog = _make_cog(_container(queue_snapshot=snapshot))
        await cog.current.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        # embed and view present
        kwargs = interaction.response.send_message.call_args.kwargs
        assert "embed" in kwargs
        assert "view" in kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_swallows_http_exception_when_fetching_original_response(self):
        _, interaction = _interaction_in_voice()
        track = _track("cur")
        snapshot = QueueSnapshot(current_track=track, tracks=[], total_tracks=0, total_duration=180)

        interaction.original_response = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(status=500), "boom")
        )

        cog = _make_cog(_container(queue_snapshot=snapshot))

        # Must not raise
        await cog.current.callback(cog, interaction)


# =============================================================================
# /played
# =============================================================================


class TestPlayed:
    @pytest.mark.asyncio
    async def test_returns_silently_when_voice_guard_fails(self):
        interaction = make_interaction(user=make_member(voice=None), guild_id=42)
        cog = _make_cog(_container(recent_tracks=[_track("a")]))

        await cog.played.callback(cog, interaction)

        cog.container.history_repository.get_recent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_silently_when_no_guild(self):
        member = make_member(member_id=1)
        member.voice = make_voice_state(channel=make_voice_channel(channel_id=10, members=[member]))
        interaction = make_interaction(user=member, has_guild=False)
        cog = _make_cog(_container(recent_tracks=[_track("a")]))

        await cog.played.callback(cog, interaction)

    @pytest.mark.asyncio
    async def test_sends_empty_message_when_no_history(self):
        _, interaction = _interaction_in_voice()
        cog = _make_cog(_container(recent_tracks=[]))

        await cog.played.callback(cog, interaction)

        sent = interaction.response.send_message.call_args
        assert "No tracks have been played yet" in sent.args[0]

    @pytest.mark.asyncio
    async def test_sends_embed_when_history_present(self):
        _, interaction = _interaction_in_voice()
        cog = _make_cog(_container(recent_tracks=[_track("a"), _track("b")]))

        await cog.played.callback(cog, interaction)

        kwargs = interaction.response.send_message.call_args.kwargs
        assert "embed" in kwargs
        assert kwargs.get("ephemeral") is True


# =============================================================================
# /user_history
# =============================================================================


class TestUserHistory:
    @pytest.mark.asyncio
    async def test_returns_silently_when_voice_guard_fails(self):
        interaction = make_interaction(user=make_member(voice=None), guild_id=42)
        target = make_member(member_id=999)
        cog = _make_cog(_container(recent_by_user=[]))

        await cog.user_history.callback(cog, interaction, user=target, page=1)

        cog.container.history_repository.get_recent_by_user.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_silently_when_no_guild(self):
        member = make_member(member_id=1)
        member.voice = make_voice_state(channel=make_voice_channel(channel_id=10, members=[member]))
        interaction = make_interaction(user=member, has_guild=False)
        target = make_member(member_id=999)
        cog = _make_cog(_container(recent_by_user=[]))

        await cog.user_history.callback(cog, interaction, user=target, page=1)

    @pytest.mark.asyncio
    async def test_sends_empty_message_when_user_has_no_history(self):
        _, interaction = _interaction_in_voice()
        target = make_member(member_id=999)
        target.display_name = "Alice"
        cog = _make_cog(_container(recent_by_user=[]))

        await cog.user_history.callback(cog, interaction, user=target, page=1)

        sent = interaction.response.send_message.call_args
        assert "No tracks found" in sent.args[0]

    @pytest.mark.asyncio
    async def test_sends_paginated_embed_when_history_present(self):
        _, interaction = _interaction_in_voice()
        target = make_member(member_id=999)
        target.display_name = "Bob"
        # 30 tracks to force pagination
        tracks = [_track(f"t{i}") for i in range(30)]
        cog = _make_cog(_container(recent_by_user=tracks))

        await cog.user_history.callback(cog, interaction, user=target, page=2)

        kwargs = interaction.response.send_message.call_args.kwargs
        assert "embed" in kwargs


# =============================================================================
# _format_history_line — branch coverage
# =============================================================================


class TestFormatHistoryLine:
    def test_with_all_fields_includes_artist_duration_likes_requester_id(self):
        track = _track("a")
        line = NowPlayingCog._format_history_line(1, track)
        assert "**1.**" in line
        assert "A" in line  # artist
        assert "3:00" in line  # duration
        assert "42 likes" in line
        assert f"<@{track.requested_by_id}>" in line

    def test_falls_back_to_uploader_when_no_artist(self):
        track = _track("a", artist=None, uploader="UploaderName")
        line = NowPlayingCog._format_history_line(1, track)
        assert "UploaderName" in line

    def test_omits_optional_fields_when_absent(self):
        track = _track(
            "a",
            artist=None,
            uploader=None,
            duration_seconds=None,
            like_count=None,
            requested_by_id=None,
            requested_by_name=None,
        )
        line = NowPlayingCog._format_history_line(1, track)
        assert "likes" not in line
        assert "<@" not in line

    def test_falls_back_to_requested_by_name_when_no_id(self):
        track = _track("a", requested_by_id=None, requested_by_name="Charlie")
        line = NowPlayingCog._format_history_line(1, track)
        assert "Charlie" in line
