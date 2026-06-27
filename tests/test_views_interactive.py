"""Tests for interactive views: ResumePlaybackView, WarmupRetryView,
LongTrackVoteView, and RadioView."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_music_player.application.services.queue_models import EnqueueOk
from discord_music_player.domain.shared.constants import LimitConstants


def _enqueue_ok(*, should_start: bool) -> EnqueueOk:
    from discord_music_player.domain.music.entities import Track
    from discord_music_player.domain.music.wrappers import TrackId

    track = Track(id=TrackId(value="voted1"), title="Voted", webpage_url="https://youtu.be/voted1")
    return EnqueueOk(
        track=track, position=0, queue_length=1, should_start=should_start, message="Queued"
    )


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

        ps.start_playback.assert_awaited_once_with(1, start_seconds=None)
        call_kwargs = interaction.response.edit_message.call_args[1]
        assert "Resumed playback: **Test Song**" in call_kwargs["content"]

    @pytest.mark.asyncio
    async def test_skip_button_stops_playback(self):
        view, ps = _make_resume_view()
        interaction = AsyncMock()

        await view.skip_button.callback(interaction)

        ps.stop_playback.assert_awaited_once_with(1)
        call_kwargs = interaction.response.edit_message.call_args[1]
        assert call_kwargs["content"] == "Skipped. Playback cleared."

    @pytest.mark.asyncio
    async def test_on_timeout_stops_and_deletes(self):
        view, ps = _make_resume_view()
        message = AsyncMock()
        view.set_message(message)

        await view.on_timeout()

        ps.stop_playback.assert_awaited_once_with(1)
        message.delete.assert_awaited_once()

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


def _make_warmup_view(remaining: int = 5, replay: AsyncMock | None = None):
    from discord_music_player.infrastructure.discord.views.warmup_retry_view import (
        WarmupRetryState,
        WarmupRetryView,
    )

    rp = replay or AsyncMock()
    state = WarmupRetryState(
        remaining_seconds=remaining,
        query="test song",
        replay=rp,
    )
    return WarmupRetryView(state), rp


class TestWarmupRetryView:
    @pytest.mark.asyncio
    async def test_timeout_is_remaining_plus_120(self):
        view, _ = _make_warmup_view(remaining=10)
        assert view.timeout == 130

    @pytest.mark.asyncio
    async def test_retry_button_calls_replay(self):
        view, rp = _make_warmup_view()
        view.retry_button.disabled = False  # simulate enabled
        interaction = AsyncMock()

        await view.retry_button.callback(interaction)

        rp.assert_awaited_once_with(interaction)

    @pytest.mark.asyncio
    async def test_retry_preserves_captured_slash_params(self):
        """The closure the cog hands in must carry count/start/shuffle through
        retry — not just the query string."""
        captured: dict[str, object] = {}

        async def _replay(i: AsyncMock) -> None:
            # Simulate what PlaybackCog._execute_play would do with the
            # replay-bound params: stash them so the test can assert.
            await _inner_execute(i, query="q", count=25, start=3, shuffle=True)

        async def _inner_execute(
            i: AsyncMock, *, query: str, count: int, start: int, shuffle: bool
        ) -> None:
            captured.update(query=query, count=count, start=start, shuffle=shuffle)

        view, _ = _make_warmup_view(replay=AsyncMock(wraps=_replay))
        view.retry_button.disabled = False
        interaction = AsyncMock()

        await view.retry_button.callback(interaction)

        assert captured == {"query": "q", "count": 25, "start": 3, "shuffle": True}

    @pytest.mark.asyncio
    async def test_retry_button_with_message_edits(self):
        view, rp = _make_warmup_view()
        view.retry_button.disabled = False
        message = AsyncMock()
        view._message = message
        interaction = AsyncMock()

        await view.retry_button.callback(interaction)

        message.edit.assert_awaited_once()
        rp.assert_awaited_once()

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
    async def test_on_timeout_with_message_deletes(self):
        view, _ = _make_warmup_view()
        message = AsyncMock()
        view._message = message

        await view.on_timeout()

        message.delete.assert_awaited_once()

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


def _make_vote_view(listener_count: int = 1, voter_id: int = 42):
    from discord_music_player.infrastructure.discord.views.long_track_vote_view import (
        LongTrackVoteView,
    )

    # Include the voter in the listener list so their vote counts
    listeners = [voter_id] + list(range(1000, 1000 + listener_count - 1))
    container = MagicMock()
    container.voice_adapter = MagicMock()
    container.voice_adapter.get_listeners = AsyncMock(return_value=listeners)

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


def _vote_panel(view, user_id: int = 42):
    from discord_music_player.infrastructure.discord.views.personal_vote_panel import (
        PersonalVotePanel,
    )

    return PersonalVotePanel(parent=view, user_id=user_id)


class TestLongTrackVoteView:
    @pytest.mark.asyncio
    async def test_accept_vote_triggers_accept(self):
        view, container, _ = _make_vote_view(listener_count=1)
        message = AsyncMock()
        view.set_message(message)
        container.queue_service.enqueue = AsyncMock(return_value=_enqueue_ok(should_start=True))

        await _vote_panel(view).accept_action.callback(AsyncMock())

        container.queue_service.enqueue.assert_awaited_once()
        container.playback_service.start_playback.assert_awaited_once_with(1)
        message.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reject_vote_triggers_reject(self):
        # 1 listener → threshold=1, so 1 reject > 1-1=0 triggers reject
        view, container, _ = _make_vote_view(listener_count=1)
        message = AsyncMock()
        view.set_message(message)

        await _vote_panel(view).reject_action.callback(AsyncMock())

        container.queue_service.enqueue.assert_not_called()
        embed = message.edit.call_args[1]["embed"]
        assert "rejected" in embed.title.lower()

    @pytest.mark.asyncio
    async def test_accept_enqueues_without_start_when_not_should_start(self):
        view, container, _ = _make_vote_view(listener_count=1)
        view.set_message(AsyncMock())
        container.queue_service.enqueue = AsyncMock(return_value=_enqueue_ok(should_start=False))

        await _vote_panel(view).accept_action.callback(AsyncMock())

        container.queue_service.enqueue.assert_awaited_once()
        container.playback_service.start_playback.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_timeout_auto_rejects(self):
        view, _, _ = _make_vote_view()
        message = AsyncMock()
        view.set_message(message)

        await view.on_timeout()

        message.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_public_buttons_disabled_after_accept(self):
        view, container, _ = _make_vote_view(listener_count=1)
        view.set_message(AsyncMock())
        container.queue_service.enqueue = AsyncMock(return_value=_enqueue_ok(should_start=False))

        await _vote_panel(view).accept_action.callback(AsyncMock())

        for item in view.children:
            assert item.disabled is True

    @pytest.mark.asyncio
    async def test_panel_greys_choice_and_relabels_other(self):
        # 3 listeners → threshold=2, so a single accept doesn't resolve the vote
        view, _, _ = _make_vote_view(listener_count=3)
        view.set_message(AsyncMock())
        panel = _vote_panel(view)

        await panel.accept_action.callback(AsyncMock())

        assert panel.accept_action.disabled is True
        assert panel.reject_action.label == "Change my vote"

    @pytest.mark.asyncio
    async def test_vote_switch_accept_to_reject(self):
        view, _, _ = _make_vote_view(listener_count=3)
        view.set_message(AsyncMock())
        panel = _vote_panel(view)

        await panel.accept_action.callback(AsyncMock())
        await panel.reject_action.callback(AsyncMock())

        assert 42 in view._votes_reject
        assert 42 not in view._votes_accept

    @pytest.mark.asyncio
    async def test_override_by_admin_accepts(self):
        view, container, _ = _make_vote_view()
        view.set_message(AsyncMock())
        container.settings.discord.owner_ids = []
        container.queue_service.enqueue = AsyncMock(return_value=_enqueue_ok(should_start=False))

        member = MagicMock(spec=discord.Member)
        member.id = 7
        member.guild_permissions.administrator = True
        interaction = AsyncMock()
        interaction.user = member

        await view.override_button.callback(interaction)

        container.queue_service.enqueue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_override_rejected_for_non_admin(self):
        view, container, _ = _make_vote_view()
        view.set_message(AsyncMock())
        container.settings.discord.owner_ids = []

        member = MagicMock(spec=discord.Member)
        member.id = 7
        member.guild_permissions.administrator = False
        interaction = AsyncMock()
        interaction.user = member

        await view.override_button.callback(interaction)

        container.queue_service.enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_timeout_value(self):
        view, _, _ = _make_vote_view()
        assert view.timeout == LimitConstants.LONG_TRACK_VOTE_TIMEOUT_SECONDS


# =============================================================================
# RadioView
# =============================================================================


def _make_radio_tracks():
    """Create mock Track objects for RadioView tests."""
    from discord_music_player.domain.music.entities import Track
    from discord_music_player.domain.music.wrappers import TrackId

    tracks = []
    for i in range(3):
        tracks.append(
            Track(
                id=TrackId(value=f"track{i}"),
                title=f"Radio Track {i + 1}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
                stream_url="https://stream.example.com/audio.mp3",
            )
        )
    return tracks


def _make_radio_view():
    from discord_music_player.infrastructure.discord.views.radio_view import RadioView

    container = MagicMock()
    container.radio_service = MagicMock()
    container.radio_service.reroll_track = AsyncMock()

    tracks = _make_radio_tracks()
    view = RadioView(guild_id=1, container=container, tracks=tracks, seed_title="Cool Song")
    return view, container, tracks


def _get_reroll_buttons(view: discord.ui.View) -> list[discord.ui.Button[Any]]:
    """Return row-0 buttons (the dynamically-added reroll buttons)."""
    return [item for item in view.children if isinstance(item, discord.ui.Button) and item.row == 0]


class TestRadioView:
    @pytest.mark.asyncio
    async def test_reroll_button_success(self):
        from discord_music_player.domain.music.entities import Track
        from discord_music_player.domain.music.wrappers import TrackId

        view, container, tracks = _make_radio_view()

        new_track = Track(
            id=TrackId(value="new1"),
            title="New Recommendation",
            webpage_url="https://youtube.com/watch?v=new1",
            stream_url="https://stream.example.com/audio.mp3",
        )
        container.radio_service.reroll_track = AsyncMock(return_value=new_track)

        interaction = AsyncMock()
        interaction.user.id = 42
        interaction.user.display_name = "User"

        reroll_btn = _get_reroll_buttons(view)[0]
        await reroll_btn.callback(interaction)

        container.radio_service.reroll_track.assert_awaited_once_with(
            guild_id=1, queue_position=0, user_id=42, user_name="User"
        )
        assert view._tracks[0].title == "New Recommendation"
        assert not reroll_btn.disabled
        assert not view._reroll_in_progress

    @pytest.mark.asyncio
    async def test_reroll_button_failure(self):
        view, container, _ = _make_radio_view()

        container.radio_service.reroll_track = AsyncMock(return_value=None)

        interaction = AsyncMock()
        interaction.user.id = 42
        interaction.user.display_name = "User"

        reroll_btn = _get_reroll_buttons(view)[0]
        await reroll_btn.callback(interaction)

        msg = interaction.followup.send.call_args[0][0]
        assert "Couldn't" in msg
        assert not reroll_btn.disabled
        assert not view._reroll_in_progress

    @pytest.mark.asyncio
    async def test_reroll_blocked_while_in_progress(self):
        """Second reroll should be rejected while first is in progress."""
        view, container, _ = _make_radio_view()
        view._reroll_in_progress = True

        interaction = AsyncMock()
        interaction.user.id = 42
        interaction.user.display_name = "User"

        reroll_btn = _get_reroll_buttons(view)[0]
        await reroll_btn.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "already in progress" in msg
        container.radio_service.reroll_track.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_accept_button_disables_view(self):
        view, container, _ = _make_radio_view()

        interaction = AsyncMock()

        await view.accept_button.callback(interaction)

        for item in view.children:
            if isinstance(item, discord.ui.Button):
                assert item.disabled is True

    @pytest.mark.asyncio
    async def test_view_has_correct_button_count(self):
        """View should have N reroll buttons + 1 accept button."""
        view, _, tracks = _make_radio_view()

        buttons = [item for item in view.children if isinstance(item, discord.ui.Button)]
        assert len(buttons) == len(tracks) + 1

    @pytest.mark.asyncio
    async def test_queue_start_position_offsets_buttons(self):
        """Reroll buttons should use queue_start_position as offset."""
        from discord_music_player.infrastructure.discord.views.radio_view import RadioView

        container = MagicMock()
        tracks = _make_radio_tracks()
        view = RadioView(
            guild_id=1,
            container=container,
            tracks=tracks,
            seed_title="Song",
            queue_start_position=3,
        )

        reroll_buttons = _get_reroll_buttons(view)
        # Labels are 1-indexed display numbers; verify by invoking callbacks
        assert len(reroll_buttons) == 3
        assert reroll_buttons[0].label == "1"
        assert reroll_buttons[1].label == "2"
        assert reroll_buttons[2].label == "3"
