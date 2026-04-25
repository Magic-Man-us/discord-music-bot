"""Targeted branch coverage for PlaybackCog — fills gaps in test_music_cog.py.

Focused on:
  - module helpers (_suggest_save_name, _format_slice_status)
  - cog_load / cog_unload event-bus subscribe / unsubscribe
  - _ensure_voice_ready rejection branches
  - _find_auto_post_channel + _auto_post_candidates
  - _on_track_started_auto_post branches
  - _on_track_finished branches
  - _on_requester_left + _on_requester_rejoined
  - voice-guard rejection on /stop, /pause, /resume, /leave, /seek, /playnext
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_music_player.application.services.queue_models import (
    BatchEnqueueResult,
    QueueSnapshot,
)
from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import StartSeconds, TrackId
from discord_music_player.infrastructure.discord.cogs.playback_cog import (
    PlaybackCog,
    _format_slice_status,
    _suggest_save_name,
)

from conftest import (  # noqa: E402  -- pytest adds tests/ to sys.path
    FakeContainer,
    FakeVoiceAdapter,
    FakeVoiceWarmupTracker,
    make_interaction,
    make_member,
    make_voice_channel,
    make_voice_state,
)


# =============================================================================
# Helper functions
# =============================================================================


class TestSuggestSaveName:
    def test_falls_back_to_source_label_when_raw_empty(self):
        assert _suggest_save_name(None, "Source Label") == "source-label"

    def test_falls_back_when_raw_only_whitespace(self):
        assert _suggest_save_name("   ", "MY SOURCE") == "my-source"

    def test_uses_lowercased_raw_when_present(self):
        assert _suggest_save_name("My Playlist", "Fallback") == "my playlist"


class TestFormatSliceStatus:
    def _slice(self, **overrides):
        from discord_music_player.utils.playlist_select import PlaylistSlice

        defaults = {
            "kept": 5,
            "total": 10,
            "start": 1,
            "shuffled": False,
            "truncated": 0,
            "tracks": [],
            "items_indices": [],
            "requested_count": 5,
        }
        defaults.update(overrides)
        return PlaylistSlice(**defaults)

    def test_basic_status(self):
        status = _format_slice_status("YouTube", self._slice(), count_override=None)
        assert "5" in status and "10" in status and "YouTube" in status

    def test_includes_start_offset(self):
        status = _format_slice_status("YT", self._slice(start=3), count_override=None)
        assert "starting at #3" in status

    def test_includes_shuffled_marker(self):
        status = _format_slice_status("YT", self._slice(shuffled=True), count_override=None)
        assert "shuffled" in status.lower()

    def test_truncation_hint_when_default_count_truncates(self):
        status = _format_slice_status(
            "YT", self._slice(truncated=2), count_override=None
        )
        assert "Default" in status

    def test_no_truncation_hint_when_count_override_set(self):
        status = _format_slice_status(
            "YT", self._slice(truncated=2), count_override=10
        )
        assert "Default" not in status


# =============================================================================
# Fixtures
# =============================================================================


def _track(track_id: str = "abc") -> Track:
    return Track(
        id=TrackId(value=track_id),
        title=f"T-{track_id}",
        webpage_url=f"https://yt/{track_id}",
        duration_seconds=180,
    )


def _container(**overrides) -> FakeContainer:
    """Build a fake container with sensible defaults for cog tests."""
    playback_service = MagicMock()
    playback_service.set_track_finished_callback = MagicMock()
    playback_service.start_playback = AsyncMock()
    playback_service.pause_playback = AsyncMock(return_value=True)
    playback_service.resume_playback = AsyncMock(return_value=True)
    playback_service.stop_playback = AsyncMock(return_value=True)
    playback_service.seek_playback = AsyncMock(return_value=True)
    playback_service.skip_track = AsyncMock(return_value=None)
    playback_service.cleanup_guild = AsyncMock()

    auto_skip = MagicMock()
    auto_skip.set_on_requester_left_callback = MagicMock()
    auto_skip.set_on_requester_rejoined_callback = MagicMock()

    msm = MagicMock()
    state = MagicMock()
    state.now_playing = None
    state.now_playing_reserved = False
    msm.get_state = MagicMock(return_value=state)
    msm.clear_all = MagicMock()
    msm.reserve_now_playing = MagicMock()
    msm.track_now_playing = MagicMock()
    msm.on_track_finished = AsyncMock()
    msm.promote_next_track = AsyncMock()
    msm.reset = AsyncMock()

    queue_service = MagicMock()
    queue_service.get_queue = AsyncMock(
        return_value=QueueSnapshot(
            current_track=_track("cur"),
            tracks=[],
            total_tracks=1,
            total_duration=180,
        )
    )
    queue_service.enqueue = AsyncMock(return_value=MagicMock(success=True, should_start=False))
    queue_service.enqueue_next = AsyncMock(return_value=MagicMock(success=True))
    queue_service.enqueue_batch = AsyncMock(return_value=BatchEnqueueResult(enqueued=0, should_start=False))
    queue_service.clear = AsyncMock(return_value=0)

    session_repository = MagicMock()
    session_repository.get = AsyncMock(return_value=None)

    settings = MagicMock()
    settings.discord.dj_role_id = None

    voice_warmup_tracker = FakeVoiceWarmupTracker(remaining=0)
    voice_adapter = FakeVoiceAdapter(connected=True)

    audio_resolver = MagicMock()
    audio_resolver.resolve = AsyncMock(return_value=None)
    audio_resolver.is_url = MagicMock(return_value=False)
    audio_resolver.is_playlist = MagicMock(return_value=False)

    radio_service = MagicMock()
    radio_service.is_enabled = MagicMock(return_value=False)
    radio_service.disable_radio = MagicMock()

    container = FakeContainer(
        playback_service=playback_service,
        auto_skip_on_requester_leave=auto_skip,
        message_state_manager=msm,
        queue_service=queue_service,
        session_repository=session_repository,
        voice_warmup_tracker=voice_warmup_tracker,
        voice_adapter=voice_adapter,
        audio_resolver=audio_resolver,
        radio_service=radio_service,
        settings=settings,
        ai_enabled=False,
    )
    for k, v in overrides.items():
        setattr(container, k, v)
    return container


def _make_cog(container=None, *, bot=None) -> PlaybackCog:
    bot = bot or MagicMock()
    return PlaybackCog(bot, container or _container())


def _interaction_in_voice(*, guild_id=42):
    member = make_member(member_id=1)
    member.voice = make_voice_state(channel=make_voice_channel(channel_id=10, members=[member]))
    interaction = make_interaction(user=member, guild_id=guild_id)
    return member, interaction


# =============================================================================
# cog_load / cog_unload — event bus subscription
# =============================================================================


class TestCogLifecycle:
    @pytest.mark.asyncio
    async def test_cog_load_subscribes_to_track_started(self):
        cog = _make_cog()
        await cog.cog_load()
        # Three callbacks set, plus event subscription stored
        cog.container.playback_service.set_track_finished_callback.assert_called_once()
        cog.container.auto_skip_on_requester_leave.set_on_requester_left_callback.assert_called_once()
        cog.container.auto_skip_on_requester_leave.set_on_requester_rejoined_callback.assert_called_once()
        assert hasattr(cog, "_event_bus")

    @pytest.mark.asyncio
    async def test_cog_unload_unsubscribes_when_loaded(self):
        cog = _make_cog()
        await cog.cog_load()
        await cog.cog_unload()
        cog.container.playback_service.set_track_finished_callback.assert_called_with(None)
        cog.container.auto_skip_on_requester_leave.set_on_requester_left_callback.assert_called_with(None)
        cog.container.message_state_manager.clear_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_without_load_does_not_unsubscribe_events(self):
        cog = _make_cog()
        await cog.cog_unload()
        cog.container.message_state_manager.clear_all.assert_called_once()


# =============================================================================
# _ensure_voice_ready — five rejection branches
# =============================================================================


class TestEnsureVoiceReady:
    @pytest.mark.asyncio
    async def test_returns_none_when_member_missing(self):
        cog = _make_cog()
        interaction = make_interaction(has_guild=False)
        result = await cog._ensure_voice_ready(interaction)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_user_not_in_voice(self):
        cog = _make_cog()
        interaction = make_interaction(user=make_member(voice=None))
        result = await cog._ensure_voice_ready(interaction)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_warmup_remaining(self):
        # Two members in channel so is_solo_in_channel = False, warmup applies
        a = make_member(member_id=1)
        b = make_member(member_id=2)
        channel = make_voice_channel(channel_id=10, members=[a, b])
        a.voice = make_voice_state(channel=channel)
        interaction = make_interaction(user=a)

        container = _container()
        container.voice_warmup_tracker = FakeVoiceWarmupTracker(remaining=15)
        cog = _make_cog(container)
        result = await cog._ensure_voice_ready(interaction)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_voice_connect_fails(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.voice_adapter = FakeVoiceAdapter(connected=False, connect_succeeds=False)
        cog = _make_cog(container)
        result = await cog._ensure_voice_ready(interaction)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_member_on_happy_path_already_connected(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.voice_adapter = FakeVoiceAdapter(connected=True)
        cog = _make_cog(container)
        result = await cog._ensure_voice_ready(interaction)
        assert result is member

    @pytest.mark.asyncio
    async def test_connects_on_happy_path_when_not_yet_connected(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        adapter = FakeVoiceAdapter(connected=False, connect_succeeds=True)
        container.voice_adapter = adapter
        cog = _make_cog(container)
        result = await cog._ensure_voice_ready(interaction)
        assert result is member
        assert adapter.ensure_connected_calls == [(42, 10)]


# =============================================================================
# _find_auto_post_channel + _auto_post_candidates
# =============================================================================


class TestFindAutoPostChannel:
    def test_returns_none_when_guild_not_found(self):
        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=None)
        cog = _make_cog(bot=bot)
        assert cog._find_auto_post_channel(42) is None

    def test_returns_first_writable_candidate(self):
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.me = MagicMock()
        guild.voice_client = None
        guild.system_channel = None

        # First candidate is unwritable; second is writable
        bad = MagicMock(spec=discord.TextChannel)
        bad.permissions_for = MagicMock(return_value=MagicMock(send_messages=False))
        good = MagicMock(spec=discord.TextChannel)
        good.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
        guild.text_channels = [bad, good]

        bot.get_guild = MagicMock(return_value=guild)
        cog = _make_cog(bot=bot)
        assert cog._find_auto_post_channel(42) is good

    def test_returns_none_when_no_writable_channel(self):
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.me = MagicMock()
        guild.voice_client = None
        guild.system_channel = None
        unwritable = MagicMock(spec=discord.TextChannel)
        unwritable.permissions_for = MagicMock(return_value=MagicMock(send_messages=False))
        guild.text_channels = [unwritable]
        bot.get_guild = MagicMock(return_value=guild)
        cog = _make_cog(bot=bot)
        assert cog._find_auto_post_channel(42) is None


# =============================================================================
# _on_track_started_auto_post
# =============================================================================


class TestOnTrackStartedAutoPost:
    def _event(self, **overrides):
        from discord_music_player.domain.shared.events import TrackStartedPlaying

        defaults = dict(
            guild_id=42,
            track_id=TrackId(value="abc"),
            track_title="Title",
            track_url="https://yt/abc",
            duration_seconds=180,
        )
        defaults.update(overrides)
        return TrackStartedPlaying(**defaults)

    @pytest.mark.asyncio
    async def test_skips_when_now_playing_reserved(self):
        container = _container()
        container.message_state_manager.get_state.return_value.now_playing_reserved = True
        cog = _make_cog(container)
        await cog._on_track_started_auto_post(self._event())
        # Should never reach session_repository
        container.session_repository.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_existing_now_playing_message(self):
        container = _container()
        container.message_state_manager.get_state.return_value.now_playing = MagicMock()
        cog = _make_cog(container)
        await cog._on_track_started_auto_post(self._event())
        container.session_repository.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_event_lacks_title_or_url(self):
        container = _container()
        cog = _make_cog(container)
        await cog._on_track_started_auto_post(self._event(track_title=None))
        container.session_repository.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_session_or_current_track_missing(self):
        container = _container()
        container.session_repository.get = AsyncMock(return_value=None)
        cog = _make_cog(container)
        await cog._on_track_started_auto_post(self._event())
        container.session_repository.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_session_current_title_does_not_match(self):
        container = _container()
        session = MagicMock()
        session.current_track = _track("other")
        session.peek = MagicMock(return_value=None)
        container.session_repository.get = AsyncMock(return_value=session)
        cog = _make_cog(container)
        await cog._on_track_started_auto_post(self._event(track_title="Title"))

    @pytest.mark.asyncio
    async def test_skips_when_no_writable_channel(self):
        container = _container()
        session = MagicMock()
        session.current_track = _track("abc")
        session.current_track = Track(
            id=TrackId(value="abc"),
            title="Matching",
            webpage_url="https://yt/abc",
            duration_seconds=180,
        )
        session.peek = MagicMock(return_value=None)
        container.session_repository.get = AsyncMock(return_value=session)
        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=None)
        cog = _make_cog(container, bot=bot)
        await cog._on_track_started_auto_post(self._event(track_title="Matching"))

    @pytest.mark.asyncio
    async def test_swallows_send_exception(self):
        container = _container()
        session = MagicMock()
        session.current_track = Track(
            id=TrackId(value="abc"),
            title="Matching",
            webpage_url="https://yt/abc",
            duration_seconds=180,
        )
        session.peek = MagicMock(return_value=None)
        container.session_repository.get = AsyncMock(return_value=session)

        # Construct a writable channel
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.me = MagicMock()
        guild.voice_client = None
        guild.system_channel = None
        channel = MagicMock(spec=discord.TextChannel)
        channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
        channel.send = AsyncMock(side_effect=RuntimeError("boom"))
        guild.text_channels = [channel]
        bot.get_guild = MagicMock(return_value=guild)

        cog = _make_cog(container, bot=bot)
        cog.logger = MagicMock()
        # Must not raise
        await cog._on_track_started_auto_post(self._event(track_title="Matching"))


# =============================================================================
# _on_track_finished
# =============================================================================


class TestOnTrackFinished:
    @pytest.mark.asyncio
    async def test_no_promotion_when_session_missing(self):
        container = _container()
        container.session_repository.get = AsyncMock(return_value=None)
        cog = _make_cog(container)
        await cog._on_track_finished(42, _track("a"))
        container.message_state_manager.on_track_finished.assert_awaited_once()
        container.message_state_manager.promote_next_track.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_promotion_when_no_next_track(self):
        container = _container()
        session = MagicMock()
        session.current_track = None
        container.session_repository.get = AsyncMock(return_value=session)
        cog = _make_cog(container)
        await cog._on_track_finished(42, _track("a"))
        container.message_state_manager.promote_next_track.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_promotes_when_next_track_present(self):
        container = _container()
        session = MagicMock()
        session.current_track = _track("next")
        session.peek = MagicMock(return_value=None)
        container.session_repository.get = AsyncMock(return_value=session)
        cog = _make_cog(container)
        await cog._on_track_finished(42, _track("a"))
        container.message_state_manager.promote_next_track.assert_awaited_once()


# =============================================================================
# _on_requester_left + _on_requester_rejoined
# =============================================================================


class TestOnRequesterLeftAndRejoined:
    @pytest.mark.asyncio
    async def test_uses_now_playing_channel_when_available(self):
        container = _container()
        msg_channel = MagicMock(spec=discord.TextChannel)
        msg_channel.send = AsyncMock(return_value=MagicMock())
        state = MagicMock()
        state.now_playing = MagicMock(channel_id=123)
        container.message_state_manager.get_state = MagicMock(return_value=state)
        bot = MagicMock()
        bot.get_channel = MagicMock(return_value=msg_channel)

        cog = _make_cog(container, bot=bot)
        await cog._on_requester_left(42, 999, _track("a"))
        msg_channel.send.assert_awaited_once()
        assert 42 in cog._requester_left_views

    @pytest.mark.asyncio
    async def test_falls_back_to_system_channel_when_now_playing_missing(self):
        container = _container()
        state = MagicMock()
        state.now_playing = None
        container.message_state_manager.get_state = MagicMock(return_value=state)

        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        sys_channel = MagicMock(spec=discord.TextChannel)
        sys_channel.send = AsyncMock(return_value=MagicMock())
        guild.system_channel = sys_channel
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_channel = MagicMock(return_value=None)

        cog = _make_cog(container, bot=bot)
        await cog._on_requester_left(42, 999, _track("a"))
        sys_channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_skips_when_no_channel_available(self):
        container = _container()
        state = MagicMock()
        state.now_playing = None
        container.message_state_manager.get_state = MagicMock(return_value=state)

        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=None)
        bot.get_channel = MagicMock(return_value=None)

        cog = _make_cog(container, bot=bot)
        cog.logger = MagicMock()
        await cog._on_requester_left(42, 999, _track("a"))
        container.playback_service.skip_track.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_rejoined_dismisses_active_view(self):
        cog = _make_cog()
        view = MagicMock()
        view.dismiss = AsyncMock()
        cog._requester_left_views[42] = view
        await cog._on_requester_rejoined(42, 999)
        view.dismiss.assert_awaited_once()
        assert 42 not in cog._requester_left_views

    @pytest.mark.asyncio
    async def test_rejoined_noop_when_no_view(self):
        cog = _make_cog()
        # No view registered — should not raise
        await cog._on_requester_rejoined(42, 999)


# =============================================================================
# Voice-guard rejection paths on simple commands
# =============================================================================


class TestVoiceGuardRejection:
    @pytest.mark.asyncio
    async def test_stop_voice_guard_fail(self):
        cog = _make_cog()
        await cog.stop.callback(cog, make_interaction(user=make_member(voice=None)))
        cog.container.playback_service.stop_playback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pause_voice_guard_fail(self):
        cog = _make_cog()
        await cog.pause.callback(cog, make_interaction(user=make_member(voice=None)))
        cog.container.playback_service.pause_playback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resume_voice_guard_fail(self):
        cog = _make_cog()
        await cog.resume.callback(cog, make_interaction(user=make_member(voice=None)))
        cog.container.playback_service.resume_playback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_leave_voice_guard_fail(self):
        cog = _make_cog()
        await cog.leave.callback(cog, make_interaction(user=make_member(voice=None)))
        cog.container.playback_service.cleanup_guild.assert_not_awaited()


# =============================================================================
# /seek branches
# =============================================================================


class TestSeekCommand:
    @pytest.mark.asyncio
    async def test_invalid_timestamp_format(self):
        member, interaction = _interaction_in_voice()
        cog = _make_cog()
        await cog.seek.callback(cog, interaction, timestamp="not-a-time")
        cog.container.playback_service.seek_playback.assert_not_awaited()
        # An error message was sent via response.send_message
        interaction.response.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_voice_guard_fail(self):
        cog = _make_cog()
        await cog.seek.callback(cog, make_interaction(user=make_member(voice=None)), timestamp="0:30")
        cog.container.playback_service.seek_playback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_happy_path_calls_seek_service(self):
        member, interaction = _interaction_in_voice()
        cog = _make_cog()
        await cog.seek.callback(cog, interaction, timestamp="1:30")
        cog.container.playback_service.seek_playback.assert_awaited_once()
        kwargs = cog.container.playback_service.seek_playback.call_args.kwargs
        assert kwargs["start_seconds"] == StartSeconds(value=90)


# =============================================================================
# /playnext branches
# =============================================================================


class TestPlaynextCommand:
    @pytest.mark.asyncio
    async def test_voice_guard_fail(self):
        cog = _make_cog()
        await cog.playnext.callback(
            cog, make_interaction(user=make_member(voice=None)), query="song"
        )
        cog.container.queue_service.enqueue_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resolver_returns_none(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.audio_resolver.resolve = AsyncMock(return_value=None)
        cog = _make_cog(container)
        await cog.playnext.callback(cog, interaction, query="missing")
        msg = interaction.followup.send.call_args.args[0]
        assert "Couldn't find" in msg

    @pytest.mark.asyncio
    async def test_enqueue_next_failure(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        resolved = _track("rsvd")
        container.audio_resolver.resolve = AsyncMock(return_value=resolved)
        container.queue_service.enqueue_next = AsyncMock(
            return_value=MagicMock(success=False, message="queue is full")
        )
        cog = _make_cog(container)
        await cog.playnext.callback(cog, interaction, query="any")
        msg = interaction.followup.send.call_args.args[0]
        assert msg == "queue is full"

    @pytest.mark.asyncio
    async def test_happy_path_sends_up_next(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        resolved = _track("rsvd")
        container.audio_resolver.resolve = AsyncMock(return_value=resolved)
        result = MagicMock(success=True, track=resolved)
        container.queue_service.enqueue_next = AsyncMock(return_value=result)
        sent = MagicMock()
        sent.delete = AsyncMock()
        interaction.followup.send = AsyncMock(return_value=sent)
        cog = _make_cog(container)
        await cog.playnext.callback(cog, interaction, query="any")
        # First positional is the "Up next:" message
        first_call_args = interaction.followup.send.call_args_list[0].args
        assert "Up next" in first_call_args[0]

    @pytest.mark.asyncio
    async def test_swallows_resolver_exception(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.audio_resolver.resolve = AsyncMock(side_effect=RuntimeError("boom"))
        cog = _make_cog(container)
        cog.logger = MagicMock()
        await cog.playnext.callback(cog, interaction, query="any")
        # Generic failure message
        msg = interaction.followup.send.call_args.args[0]
        assert "Command failed" in msg


class TestSeekZeroAndOutcomes:
    @pytest.mark.asyncio
    async def test_zero_timestamp_rejected(self):
        member, interaction = _interaction_in_voice()
        cog = _make_cog()
        await cog.seek.callback(cog, interaction, timestamp="0")
        msg = interaction.response.send_message.call_args.args[0]
        assert "greater than 0" in msg

    @pytest.mark.asyncio
    async def test_seek_returns_false_message(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.playback_service.seek_playback = AsyncMock(return_value=False)
        cog = _make_cog(container)
        await cog.seek.callback(cog, interaction, timestamp="0:30")
        # Latest send_message is the "Nothing is playing to seek" reply
        msg = interaction.response.send_message.call_args.args[0]
        assert "Nothing is playing" in msg

    @pytest.mark.asyncio
    async def test_seek_success_message(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.playback_service.seek_playback = AsyncMock(return_value=True)
        cog = _make_cog(container)
        await cog.seek.callback(cog, interaction, timestamp="1:30")
        msg = interaction.response.send_message.call_args.args[0]
        assert "Seeked to" in msg


class TestSimpleCommandSuccessMessages:
    @pytest.mark.asyncio
    async def test_stop_success(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.playback_service.stop_playback = AsyncMock(return_value=True)
        cog = _make_cog(container)
        await cog.stop.callback(cog, interaction)
        container.playback_service.stop_playback.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_pause_success(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.playback_service.pause_playback = AsyncMock(return_value=True)
        cog = _make_cog(container)
        await cog.pause.callback(cog, interaction)
        container.playback_service.pause_playback.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_resume_success(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.playback_service.resume_playback = AsyncMock(return_value=True)
        cog = _make_cog(container)
        await cog.resume.callback(cog, interaction)
        container.playback_service.resume_playback.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_leave_success(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.playback_service.cleanup_guild = AsyncMock()
        cog = _make_cog(container)
        await cog.leave.callback(cog, interaction)
        container.playback_service.cleanup_guild.assert_awaited_once_with(42)
