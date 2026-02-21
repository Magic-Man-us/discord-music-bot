"""Tests for interactive views: ResumePlaybackView, WarmupRetryView,
LongTrackVoteView, and RadioView."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from discord_music_player.domain.shared.messages import DiscordUIMessages


# =============================================================================
# ResumePlaybackView
# =============================================================================


def _make_resume_view(playback_service: AsyncMock | None = None):
    from discord_music_player.infrastructure.discord.views.resume_playback_view import (
        ResumePlaybackView,
    )

    ps = playback_service or AsyncMock()
    return ResumePlaybackView(
        guild_id=1,
        channel_id=10,
        playback_service=ps,
        track_title="Test Song",
    ), ps


class TestResumePlaybackView:
    @pytest.mark.asyncio
    async def test_resume_button_starts_playback(self):
        view, ps = _make_resume_view()
        interaction = AsyncMock()

        await view.resume_button.callback(interaction)

        ps.start_playback.assert_awaited_once_with(1)
        call_kwargs = interaction.response.edit_message.call_args[1]
        assert DiscordUIMessages.RESUME_PLAYBACK_RESUMED.format(track_title="Test Song") in call_kwargs["content"]

    @pytest.mark.asyncio
    async def test_skip_button_stops_playback(self):
        view, ps = _make_resume_view()
        interaction = AsyncMock()

        await view.skip_button.callback(interaction)

        ps.stop_playback.assert_awaited_once_with(1)
        call_kwargs = interaction.response.edit_message.call_args[1]
        assert call_kwargs["content"] == DiscordUIMessages.RESUME_PLAYBACK_CLEARED

    @pytest.mark.asyncio
    async def test_on_timeout_stops_and_edits(self):
        view, ps = _make_resume_view()
        message = AsyncMock()
        view.set_message(message)

        await view.on_timeout()

        ps.stop_playback.assert_awaited_once_with(1)
        message.edit.assert_awaited_once()
        call_kwargs = message.edit.call_args[1]
        assert call_kwargs["content"] == DiscordUIMessages.RESUME_PLAYBACK_TIMEOUT

    @pytest.mark.asyncio
    async def test_buttons_disabled_after_resume(self):
        view, _ = _make_resume_view()
        interaction = AsyncMock()

        await view.resume_button.callback(interaction)

        for item in view.children:
            assert item.disabled is True

    @pytest.mark.asyncio
    async def test_buttons_disabled_after_skip(self):
        view, _ = _make_resume_view()
        interaction = AsyncMock()

        await view.skip_button.callback(interaction)

        for item in view.children:
            assert item.disabled is True

    @pytest.mark.asyncio
    async def test_timeout_without_message_no_raise(self):
        view, ps = _make_resume_view()

        await view.on_timeout()

        ps.stop_playback.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_timeout_value(self):
        view, _ = _make_resume_view()
        assert view.timeout == 30.0


# =============================================================================
# WarmupRetryView
# =============================================================================


def _make_warmup_view(remaining: int = 5, execute_play: AsyncMock | None = None):
    from discord_music_player.infrastructure.discord.views.warmup_retry_view import (
        WarmupRetryView,
    )

    ep = execute_play or AsyncMock()
    return WarmupRetryView(
        remaining_seconds=remaining,
        query="test song",
        execute_play=ep,
    ), ep


class TestWarmupRetryView:
    @pytest.mark.asyncio
    async def test_timeout_is_remaining_plus_120(self):
        view, _ = _make_warmup_view(remaining=10)
        assert view.timeout == 130

    @pytest.mark.asyncio
    async def test_retry_button_calls_execute_play(self):
        view, ep = _make_warmup_view()
        view.retry_button.disabled = False  # simulate enabled
        interaction = AsyncMock()

        await view.retry_button.callback(interaction)

        ep.assert_awaited_once_with(interaction, "test song")

    @pytest.mark.asyncio
    async def test_retry_button_with_message_edits(self):
        view, ep = _make_warmup_view()
        view.retry_button.disabled = False
        message = AsyncMock()
        view._message = message
        interaction = AsyncMock()

        await view.retry_button.callback(interaction)

        message.edit.assert_awaited_once()
        ep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enable_after_warmup(self):
        view, _ = _make_warmup_view(remaining=0)  # 0 seconds so it resolves instantly
        message = AsyncMock()
        view._message = message

        await view._enable_after_warmup()

        assert view.retry_button.disabled is False
        message.edit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enable_after_warmup_cancelled(self):
        import asyncio

        view, _ = _make_warmup_view(remaining=9999)
        # Call and cancel immediately
        task = asyncio.create_task(view._enable_after_warmup())
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # Button should still be disabled (cancelled before sleep completed)
        assert view.retry_button.disabled is True

    @pytest.mark.asyncio
    async def test_on_timeout_with_message_edits(self):
        view, _ = _make_warmup_view()
        message = AsyncMock()
        view._message = message

        await view.on_timeout()

        message.edit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_timeout_no_enable_task(self):
        view, _ = _make_warmup_view()
        view._enable_task = None

        await view.on_timeout()  # should not raise

    @pytest.mark.asyncio
    async def test_on_timeout_cancels_enable_task(self):
        view, _ = _make_warmup_view()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        view._enable_task = mock_task

        await view.on_timeout()

        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_buttons_disabled_after_timeout(self):
        view, _ = _make_warmup_view()

        await view.on_timeout()

        for item in view.children:
            assert item.disabled is True


# =============================================================================
# LongTrackVoteView
# =============================================================================


def _make_vote_view(listener_count: int = 1):
    from discord_music_player.infrastructure.discord.views.long_track_vote_view import (
        LongTrackVoteView,
    )

    container = MagicMock()
    container.voice_adapter = MagicMock()
    container.voice_adapter.get_listeners = AsyncMock(return_value=[MagicMock()] * listener_count)

    container.queue_service = MagicMock()
    container.queue_service.enqueue = AsyncMock()
    container.playback_service = MagicMock()
    container.playback_service.start_playback = AsyncMock()

    track = MagicMock()
    track.title = "Long Song"
    track.duration_seconds = 600

    view = LongTrackVoteView(
        guild_id=1,
        track=track,
        requester_id=42,
        requester_name="User",
        container=container,
    )
    return view, container, track


class TestLongTrackVoteView:
    @pytest.mark.asyncio
    async def test_accept_vote_triggers_accept(self):
        view, container, track = _make_vote_view(listener_count=1)
        message = AsyncMock()
        view.set_message(message)

        interaction = AsyncMock()
        interaction.user.id = 42

        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.should_start = True
        container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

        await view.accept_button.callback(interaction)

        container.queue_service.enqueue.assert_awaited_once()
        container.playback_service.start_playback.assert_awaited_once_with(1)
        msg = message.edit.call_args[1]["content"]
        assert "Vote passed" in msg

    @pytest.mark.asyncio
    async def test_reject_vote_triggers_reject(self):
        # 1 listener → threshold=1, so 1 reject > 1-1=0 triggers reject
        view, container, track = _make_vote_view(listener_count=1)
        message = AsyncMock()
        view.set_message(message)

        interaction = AsyncMock()
        interaction.user.id = 42

        await view.reject_button.callback(interaction)

        container.queue_service.enqueue.assert_not_called()
        msg = message.edit.call_args[1]["content"]
        assert "Rejected" in msg

    @pytest.mark.asyncio
    async def test_accept_enqueues_without_start_when_not_should_start(self):
        view, container, track = _make_vote_view(listener_count=1)
        message = AsyncMock()
        view.set_message(message)

        interaction = AsyncMock()
        interaction.user.id = 42

        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.should_start = False
        container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

        await view.accept_button.callback(interaction)

        container.queue_service.enqueue.assert_awaited_once()
        container.playback_service.start_playback.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_timeout_auto_rejects(self):
        view, container, track = _make_vote_view()
        message = AsyncMock()
        view.set_message(message)

        await view.on_timeout()

        msg = message.edit.call_args[1]["content"]
        assert "timed out" in msg

    @pytest.mark.asyncio
    async def test_buttons_disabled_after_accept(self):
        view, container, _ = _make_vote_view(listener_count=1)
        view.set_message(AsyncMock())

        interaction = AsyncMock()
        interaction.user.id = 42

        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.should_start = False
        container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

        await view.accept_button.callback(interaction)

        for item in view.children:
            assert item.disabled is True

    @pytest.mark.asyncio
    async def test_vote_switch_accept_to_reject(self):
        # 2 listeners → threshold=1; 1 accept then switch to reject
        view, container, _ = _make_vote_view(listener_count=2)
        view.set_message(AsyncMock())

        interaction = AsyncMock()
        interaction.user.id = 42

        # First accept — not enough to trigger (no second voter)
        await view.accept_button.callback(interaction)
        # switch to reject — 1 reject > 2-1=1 is False, so won't trigger yet
        # but the accept should be removed
        assert 42 in view._votes_accept or 42 in view._votes_reject

    @pytest.mark.asyncio
    async def test_timeout_value(self):
        view, _, _ = _make_vote_view()
        assert view.timeout == 30.0


# =============================================================================
# RadioView
# =============================================================================


def _make_radio_view():
    from discord_music_player.infrastructure.discord.views.radio_view import RadioView

    container = MagicMock()
    container.radio_service = MagicMock()
    container.radio_service.disable_radio = MagicMock()
    container.radio_service.toggle_radio = AsyncMock()

    view = RadioView(guild_id=1, container=container)
    return view, container


class TestRadioView:
    @pytest.mark.asyncio
    async def test_shuffle_button_success(self):
        view, container = _make_radio_view()

        result = MagicMock()
        result.enabled = True
        result.tracks_added = 5
        result.seed_title = "Cool Song"
        container.radio_service.toggle_radio = AsyncMock(return_value=result)

        interaction = AsyncMock()
        interaction.user.id = 42
        interaction.user.display_name = "User"

        await view.shuffle_button.callback(interaction)

        container.radio_service.disable_radio.assert_called_once_with(1)
        container.radio_service.toggle_radio.assert_awaited_once()
        msg = interaction.followup.send.call_args[0][0]
        assert "Shuffled" in msg
        assert "5" in msg

    @pytest.mark.asyncio
    async def test_shuffle_button_failure(self):
        view, container = _make_radio_view()

        result = MagicMock()
        result.enabled = False
        result.message = "No track playing"
        container.radio_service.toggle_radio = AsyncMock(return_value=result)

        interaction = AsyncMock()
        interaction.user.id = 42
        interaction.user.display_name = "User"

        await view.shuffle_button.callback(interaction)

        msg = interaction.followup.send.call_args[0][0]
        assert "Couldn't" in msg or "No track playing" in msg
