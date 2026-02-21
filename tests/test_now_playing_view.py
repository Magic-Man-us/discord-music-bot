"""Unit tests for NowPlayingView."""

from __future__ import annotations

import asyncio
import urllib.parse
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_music_player.domain.shared.messages import DiscordUIMessages


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def mock_discord_event_loop():
    """Mock the event loop for Discord UI views."""
    loop = MagicMock(spec=asyncio.AbstractEventLoop)
    future = MagicMock()
    loop.create_future.return_value = future
    with patch("asyncio.get_running_loop", return_value=loop):
        yield loop


def _make_container():
    container = MagicMock()
    container.session_repository = MagicMock()
    container.session_repository.get = AsyncMock(return_value=None)
    container.shuffle_ai_client = MagicMock()
    container.shuffle_ai_client.get_recommendations = AsyncMock(return_value=[])
    container.audio_resolver = MagicMock()
    container.audio_resolver.resolve = AsyncMock(return_value=None)
    container.queue_service = MagicMock()
    container.queue_service.enqueue_next = AsyncMock()
    return container


def _make_view(*, container=None, webpage_url="https://www.youtube.com/watch?v=abc123", title="Test Song", guild_id=1):
    from discord_music_player.infrastructure.discord.views.now_playing_view import (
        NowPlayingView,
    )

    c = container or _make_container()
    view = NowPlayingView(
        webpage_url=webpage_url,
        title=title,
        guild_id=guild_id,
        container=c,
    )
    return view, c


def _make_track(title="Test Song", artist="Test Artist", webpage_url="https://youtube.com/watch?v=abc"):
    track = MagicMock()
    track.title = title
    track.artist = artist
    track.uploader = "Uploader"
    track.webpage_url = webpage_url
    track.is_from_recommendation = False
    track.model_copy = MagicMock(return_value=track)
    return track


def _make_interaction(user_id=42, display_name="TestUser"):
    interaction = AsyncMock()
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.user.name = "testuser"
    interaction.user.display_name = display_name
    return interaction


# =============================================================================
# Initialization Tests
# =============================================================================


class TestNowPlayingViewInit:
    def test_stores_attributes(self):
        view, container = _make_view(
            webpage_url="https://youtube.com/watch?v=xyz",
            title="My Song",
            guild_id=42,
        )
        assert view.webpage_url == "https://youtube.com/watch?v=xyz"
        assert view.title == "My Song"
        assert view.guild_id == 42
        assert view.container is container

    def test_default_timeout(self):
        view, _ = _make_view()
        assert view.timeout == 300.0

    def test_custom_timeout(self):
        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        container = _make_container()
        view = NowPlayingView(
            webpage_url="https://youtube.com/watch?v=abc",
            title="Song",
            guild_id=1,
            container=container,
            timeout=600.0,
        )
        assert view.timeout == 600.0

    def test_has_youtube_link_button(self):
        view, _ = _make_view(webpage_url="https://youtube.com/watch?v=test")
        link_buttons = [
            item for item in view.children
            if isinstance(item, discord.ui.Button) and item.style == discord.ButtonStyle.link
        ]
        youtube_btn = [b for b in link_buttons if "YouTube" in (b.label or "")]
        assert len(youtube_btn) == 1
        assert youtube_btn[0].url == "https://youtube.com/watch?v=test"

    def test_has_download_link_button(self):
        url = "https://youtube.com/watch?v=test"
        view, _ = _make_view(webpage_url=url)
        link_buttons = [
            item for item in view.children
            if isinstance(item, discord.ui.Button) and item.style == discord.ButtonStyle.link
        ]
        download_btn = [b for b in link_buttons if "Download" in (b.label or "")]
        assert len(download_btn) == 1
        expected_cobalt = f"https://cobalt.tools/#{urllib.parse.quote(url, safe='')}"
        assert download_btn[0].url == expected_cobalt

    def test_has_shuffle_button(self):
        view, _ = _make_view()
        shuffle_buttons = [
            item for item in view.children
            if isinstance(item, discord.ui.Button) and "Shuffle" in (item.label or "")
        ]
        assert len(shuffle_buttons) == 1
        assert shuffle_buttons[0].style == discord.ButtonStyle.primary


# =============================================================================
# Guild Lock Tests
# =============================================================================


class TestGuildLock:
    def test_get_lock_returns_same_lock_for_same_guild(self):
        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        lock1 = NowPlayingView._get_lock(999)
        lock2 = NowPlayingView._get_lock(999)
        assert lock1 is lock2
        # Cleanup
        NowPlayingView._guild_locks.pop(999, None)

    def test_get_lock_returns_different_lock_for_different_guild(self):
        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        lock1 = NowPlayingView._get_lock(997)
        lock2 = NowPlayingView._get_lock(998)
        assert lock1 is not lock2
        # Cleanup
        NowPlayingView._guild_locks.pop(997, None)
        NowPlayingView._guild_locks.pop(998, None)


# =============================================================================
# interaction_check Tests
# =============================================================================


class TestInteractionCheck:
    @pytest.mark.asyncio
    async def test_delegates_to_check_user_in_voice(self):
        view, _ = _make_view(guild_id=42)
        interaction = _make_interaction()

        with patch(
            "discord_music_player.infrastructure.discord.views.now_playing_view.check_user_in_voice",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_check:
            result = await view.interaction_check(interaction)

        assert result is True
        mock_check.assert_awaited_once_with(interaction, 42)

    @pytest.mark.asyncio
    async def test_returns_false_when_not_in_voice(self):
        view, _ = _make_view()
        interaction = _make_interaction()

        with patch(
            "discord_music_player.infrastructure.discord.views.now_playing_view.check_user_in_voice",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await view.interaction_check(interaction)

        assert result is False


# =============================================================================
# Shuffle Button Tests
# =============================================================================


class TestShuffleButton:
    @pytest.mark.asyncio
    async def test_shuffle_lock_already_held_sends_ephemeral(self):
        view, _ = _make_view(guild_id=500)
        interaction = _make_interaction()

        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        lock = NowPlayingView._get_lock(500)
        await lock.acquire()

        try:
            await view.shuffle_button.callback(interaction)

            interaction.response.send_message.assert_awaited_once_with(
                DiscordUIMessages.SHUFFLE_ALREADY_IN_PROGRESS, ephemeral=True
            )
        finally:
            lock.release()
            NowPlayingView._guild_locks.pop(500, None)

    @pytest.mark.asyncio
    async def test_shuffle_no_session_sends_nothing_playing(self):
        container = _make_container()
        container.session_repository.get = AsyncMock(return_value=None)
        view, _ = _make_view(container=container, guild_id=501)
        interaction = _make_interaction()

        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        try:
            await view.shuffle_button.callback(interaction)

            interaction.response.defer.assert_awaited_once_with(ephemeral=True)
            interaction.followup.send.assert_awaited_once_with(
                DiscordUIMessages.STATE_NOTHING_PLAYING, ephemeral=True
            )
        finally:
            NowPlayingView._guild_locks.pop(501, None)

    @pytest.mark.asyncio
    async def test_shuffle_session_no_current_track_sends_nothing_playing(self):
        container = _make_container()
        session = MagicMock()
        session.current_track = None
        container.session_repository.get = AsyncMock(return_value=session)
        view, _ = _make_view(container=container, guild_id=502)
        interaction = _make_interaction()

        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        try:
            await view.shuffle_button.callback(interaction)

            interaction.followup.send.assert_awaited_once_with(
                DiscordUIMessages.STATE_NOTHING_PLAYING, ephemeral=True
            )
        finally:
            NowPlayingView._guild_locks.pop(502, None)

    @pytest.mark.asyncio
    async def test_shuffle_no_recommendations_sends_error(self):
        container = _make_container()
        session = MagicMock()
        session.current_track = _make_track()
        container.session_repository.get = AsyncMock(return_value=session)
        container.shuffle_ai_client.get_recommendations = AsyncMock(return_value=[])
        view, _ = _make_view(container=container, guild_id=503)
        interaction = _make_interaction()

        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        try:
            await view.shuffle_button.callback(interaction)

            interaction.followup.send.assert_awaited_once_with(
                DiscordUIMessages.SHUFFLE_NO_RECOMMENDATION, ephemeral=True
            )
        finally:
            NowPlayingView._guild_locks.pop(503, None)

    @pytest.mark.asyncio
    async def test_shuffle_track_not_resolved_sends_not_found(self):
        container = _make_container()
        session = MagicMock()
        session.current_track = _make_track()
        container.session_repository.get = AsyncMock(return_value=session)

        rec = MagicMock()
        rec.query = "Artist - Song"
        rec.display_text = "Artist - Song"
        container.shuffle_ai_client.get_recommendations = AsyncMock(return_value=[rec])
        container.audio_resolver.resolve = AsyncMock(return_value=None)

        view, _ = _make_view(container=container, guild_id=504)
        interaction = _make_interaction()

        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        try:
            await view.shuffle_button.callback(interaction)

            interaction.followup.send.assert_awaited_once_with(
                DiscordUIMessages.SHUFFLE_TRACK_NOT_FOUND.format(display_text="Artist - Song"),
                ephemeral=True,
            )
        finally:
            NowPlayingView._guild_locks.pop(504, None)

    @pytest.mark.asyncio
    async def test_shuffle_enqueue_fails_sends_result_message(self):
        container = _make_container()
        session = MagicMock()
        current = _make_track()
        session.current_track = current
        container.session_repository.get = AsyncMock(return_value=session)

        rec = MagicMock()
        rec.query = "Artist - Song"
        container.shuffle_ai_client.get_recommendations = AsyncMock(return_value=[rec])

        resolved_track = _make_track(title="Resolved Song")
        container.audio_resolver.resolve = AsyncMock(return_value=resolved_track)

        enqueue_result = MagicMock()
        enqueue_result.success = False
        enqueue_result.message = "Queue is full"
        container.queue_service.enqueue_next = AsyncMock(return_value=enqueue_result)

        view, _ = _make_view(container=container, guild_id=505)
        interaction = _make_interaction()

        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        try:
            await view.shuffle_button.callback(interaction)

            interaction.followup.send.assert_awaited_once_with("Queue is full", ephemeral=True)
        finally:
            NowPlayingView._guild_locks.pop(505, None)

    @pytest.mark.asyncio
    async def test_shuffle_success_sends_confirmation(self):
        container = _make_container()
        session = MagicMock()
        current = _make_track()
        session.current_track = current
        container.session_repository.get = AsyncMock(return_value=session)

        rec = MagicMock()
        rec.query = "Artist - Song"
        container.shuffle_ai_client.get_recommendations = AsyncMock(return_value=[rec])

        resolved_track = _make_track(title="Shuffled Song")
        container.audio_resolver.resolve = AsyncMock(return_value=resolved_track)

        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.track = resolved_track
        container.queue_service.enqueue_next = AsyncMock(return_value=enqueue_result)

        view, _ = _make_view(container=container, guild_id=506)
        interaction = _make_interaction()

        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        try:
            await view.shuffle_button.callback(interaction)

            msg = interaction.followup.send.call_args[0][0]
            assert "Shuffled Song" in msg
        finally:
            NowPlayingView._guild_locks.pop(506, None)

    @pytest.mark.asyncio
    async def test_shuffle_success_updates_embed_when_message_set(self):
        container = _make_container()
        session = MagicMock()
        current = _make_track()
        session.current_track = current
        container.session_repository.get = AsyncMock(return_value=session)

        rec = MagicMock()
        rec.query = "Artist - Song"
        container.shuffle_ai_client.get_recommendations = AsyncMock(return_value=[rec])

        resolved_track = _make_track(title="Shuffled Song")
        container.audio_resolver.resolve = AsyncMock(return_value=resolved_track)

        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.track = resolved_track
        container.queue_service.enqueue_next = AsyncMock(return_value=enqueue_result)

        view, _ = _make_view(container=container, guild_id=507)
        message = AsyncMock()
        view.set_message(message)
        interaction = _make_interaction()

        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        try:
            await view.shuffle_button.callback(interaction)

            # Message should have been edited (button disable + embed update)
            assert message.edit.await_count >= 1
        finally:
            NowPlayingView._guild_locks.pop(507, None)

    @pytest.mark.asyncio
    async def test_shuffle_exception_sends_error_and_restores_button(self):
        container = _make_container()
        session = MagicMock()
        session.current_track = _make_track()
        container.session_repository.get = AsyncMock(return_value=session)
        container.shuffle_ai_client.get_recommendations = AsyncMock(
            side_effect=RuntimeError("API down")
        )

        view, _ = _make_view(container=container, guild_id=508)
        interaction = _make_interaction()

        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        try:
            await view.shuffle_button.callback(interaction)

            interaction.followup.send.assert_awaited_once_with(
                DiscordUIMessages.SHUFFLE_ERROR, ephemeral=True
            )
            # Button should be re-enabled after error
            shuffle_btn = [
                item for item in view.children
                if isinstance(item, discord.ui.Button) and "Shuffle" in (item.label or "")
            ]
            assert len(shuffle_btn) == 1
            assert shuffle_btn[0].disabled is False
        finally:
            NowPlayingView._guild_locks.pop(508, None)

    @pytest.mark.asyncio
    async def test_shuffle_uses_result_track_over_resolved(self):
        """When enqueue_next returns a track, it should be used for the confirmation."""
        container = _make_container()
        session = MagicMock()
        session.current_track = _make_track()
        container.session_repository.get = AsyncMock(return_value=session)

        rec = MagicMock()
        rec.query = "query"
        container.shuffle_ai_client.get_recommendations = AsyncMock(return_value=[rec])

        resolved = _make_track(title="Resolved Title")
        container.audio_resolver.resolve = AsyncMock(return_value=resolved)

        result_track = _make_track(title="Result Title")
        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.track = result_track
        container.queue_service.enqueue_next = AsyncMock(return_value=enqueue_result)

        view, _ = _make_view(container=container, guild_id=509)
        interaction = _make_interaction()

        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        try:
            await view.shuffle_button.callback(interaction)

            msg = interaction.followup.send.call_args[0][0]
            assert "Result Title" in msg
        finally:
            NowPlayingView._guild_locks.pop(509, None)

    @pytest.mark.asyncio
    async def test_shuffle_falls_back_to_resolved_track_when_result_track_none(self):
        """When result.track is None, fallback to the resolved track."""
        container = _make_container()
        session = MagicMock()
        session.current_track = _make_track()
        container.session_repository.get = AsyncMock(return_value=session)

        rec = MagicMock()
        rec.query = "query"
        container.shuffle_ai_client.get_recommendations = AsyncMock(return_value=[rec])

        resolved = _make_track(title="Fallback Title")
        container.audio_resolver.resolve = AsyncMock(return_value=resolved)

        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.track = None
        container.queue_service.enqueue_next = AsyncMock(return_value=enqueue_result)

        view, _ = _make_view(container=container, guild_id=510)
        interaction = _make_interaction()

        from discord_music_player.infrastructure.discord.views.now_playing_view import (
            NowPlayingView,
        )

        try:
            await view.shuffle_button.callback(interaction)

            msg = interaction.followup.send.call_args[0][0]
            assert "Fallback Title" in msg
        finally:
            NowPlayingView._guild_locks.pop(510, None)


# =============================================================================
# _try_edit_message Tests
# =============================================================================


class TestTryEditMessage:
    @pytest.mark.asyncio
    async def test_no_message_is_noop(self):
        view, _ = _make_view()
        # _message is None by default
        await view._try_edit_message()  # should not raise

    @pytest.mark.asyncio
    async def test_edit_with_embed(self):
        view, _ = _make_view()
        message = AsyncMock()
        view._message = message
        embed = MagicMock(spec=discord.Embed)

        await view._try_edit_message(embed=embed)

        message.edit.assert_awaited_once_with(embed=embed, view=view)

    @pytest.mark.asyncio
    async def test_edit_without_embed(self):
        view, _ = _make_view()
        message = AsyncMock()
        view._message = message

        await view._try_edit_message()

        message.edit.assert_awaited_once_with(view=view)

    @pytest.mark.asyncio
    async def test_http_exception_is_silenced(self):
        view, _ = _make_view()
        message = AsyncMock()
        message.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "error"))
        view._message = message

        await view._try_edit_message()  # should not raise
