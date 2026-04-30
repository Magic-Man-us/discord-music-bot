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
from discord_music_player.infrastructure.discord.services.activity import (
    APPLE_MUSIC_APP_ID,
    extract_listening_query,
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

    auto_dj = MagicMock()
    auto_dj.disable = MagicMock()

    follow_mode = MagicMock()
    follow_mode.disable = MagicMock()

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
        auto_dj=auto_dj,
        follow_mode=follow_mode,
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


# =============================================================================
# /play — timestamp parsing branches
# =============================================================================


class TestPlayCommandTimestamp:
    @pytest.mark.asyncio
    async def test_invalid_timestamp_rejects(self):
        member, interaction = _interaction_in_voice()
        cog = _make_cog()
        await cog.play.callback(cog, interaction, query="some song", timestamp="garbage")
        msg = interaction.response.send_message.call_args.args[0]
        assert "Invalid timestamp" in msg

    @pytest.mark.asyncio
    async def test_valid_timestamp_proceeds_to_execute_play(self):
        member, interaction = _interaction_in_voice()
        cog = _make_cog()
        cog._execute_play = AsyncMock()
        await cog.play.callback(cog, interaction, query="song", timestamp="1:30")
        cog._execute_play.assert_awaited_once()
        # Verify start_seconds was passed
        kwargs = cog._execute_play.call_args.kwargs
        assert kwargs["start_seconds"] is not None
        assert kwargs["start_seconds"].value == 90


# =============================================================================
# _execute_play branches: spotify rejection, external URL extract, playlist
# routing, warmup retry view, voice connect failure
# =============================================================================


class TestExecutePlayBranches:
    @pytest.mark.asyncio
    async def test_no_member_returns(self):
        cog = _make_cog()
        i = make_interaction(has_guild=False)
        await cog._execute_play(i, "any")
        cog.container.queue_service.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_user_not_in_voice_returns(self):
        cog = _make_cog()
        i = make_interaction(user=make_member(voice=None))
        await cog._execute_play(i, "any")

    @pytest.mark.asyncio
    async def test_voice_connect_failure_returns(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.voice_adapter = FakeVoiceAdapter(connected=False, connect_succeeds=False)
        cog = _make_cog(container)
        await cog._execute_play(interaction, "any query")
        # Must not have attempted enqueue
        container.queue_service.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_warmup_remaining_shows_retry_view(self):
        # Two members in channel so warmup applies
        a = make_member(member_id=1)
        b = make_member(member_id=2)
        channel = make_voice_channel(channel_id=10, members=[a, b])
        a.voice = make_voice_state(channel=channel)
        interaction = make_interaction(user=a)

        container = _container()
        container.voice_warmup_tracker = FakeVoiceWarmupTracker(remaining=20)
        sent = MagicMock()
        interaction.followup.send = AsyncMock(return_value=sent)

        cog = _make_cog(container)
        await cog._execute_play(interaction, "song")

        # The followup should have been called with the warmup message
        msg = interaction.followup.send.call_args.args[0]
        assert "20s" in msg

    @pytest.mark.asyncio
    async def test_spotify_playlist_url_rejected(self):
        member, interaction = _interaction_in_voice()
        cog = _make_cog()
        await cog._execute_play(interaction, "https://open.spotify.com/playlist/abcdef")
        # An ephemeral was sent indicating Spotify isn't supported
        # Guard already responded; the rejection comes via send_ephemeral
        # Since the response is fresh, response.send_message handles it
        sent = interaction.response.send_message.call_args.args[0]
        assert "Spotify" in sent

    @pytest.mark.asyncio
    async def test_playlist_url_routes_to_handle_playlist(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.audio_resolver.is_url = MagicMock(return_value=True)
        container.audio_resolver.is_playlist = MagicMock(return_value=True)
        cog = _make_cog(container)
        cog._handle_playlist = AsyncMock()
        await cog._execute_play(interaction, "https://yt/playlist")
        cog._handle_playlist.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_single_track_routes_to_play_track(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.audio_resolver.is_url = MagicMock(return_value=False)
        container.audio_resolver.is_playlist = MagicMock(return_value=False)
        cog = _make_cog(container)
        cog._play_track = AsyncMock()
        await cog._execute_play(interaction, "some query")
        cog._play_track.assert_awaited_once()


# =============================================================================
# _play_track branches
# =============================================================================


class TestPlayTrack:
    @pytest.mark.asyncio
    async def test_no_guild_returns(self):
        cog = _make_cog()
        i = make_interaction(has_guild=False)
        await cog._play_track(i, "song")
        cog.container.queue_service.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resolver_returns_none(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.audio_resolver.resolve = AsyncMock(return_value=None)
        cog = _make_cog(container)
        await cog._play_track(interaction, "missing")
        msg = interaction.followup.send.call_args.args[0]
        assert "Couldn't find" in msg

    @pytest.mark.asyncio
    async def test_long_track_vote_intercepts(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.audio_resolver.resolve = AsyncMock(return_value=_track("long"))
        cog = _make_cog(container)
        cog._start_long_track_vote = AsyncMock(return_value=True)
        await cog._play_track(interaction, "any")
        # Should have stopped before enqueue
        container.queue_service.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enqueue_failure_shows_message(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.audio_resolver.resolve = AsyncMock(return_value=_track("song"))
        container.queue_service.enqueue = AsyncMock(
            return_value=MagicMock(success=False, message="queue is full")
        )
        cog = _make_cog(container)
        cog._start_long_track_vote = AsyncMock(return_value=False)
        await cog._play_track(interaction, "any")
        msg = interaction.followup.send.call_args.args[0]
        assert msg == "queue is full"

    @pytest.mark.asyncio
    async def test_should_start_starts_playback_and_sends_now_playing(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        resolved = _track("rsvd")
        container.audio_resolver.resolve = AsyncMock(return_value=resolved)
        container.queue_service.enqueue = AsyncMock(
            return_value=MagicMock(success=True, should_start=True, track=resolved, position=0)
        )
        cog = _make_cog(container)
        cog._start_long_track_vote = AsyncMock(return_value=False)
        cog._send_now_playing = AsyncMock()
        cog._send_queued = AsyncMock()
        await cog._play_track(interaction, "any")
        container.playback_service.start_playback.assert_awaited_once()
        cog._send_now_playing.assert_awaited_once()
        cog._send_queued.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_should_start_routes_to_send_queued(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        resolved = _track("rsvd")
        container.audio_resolver.resolve = AsyncMock(return_value=resolved)
        container.queue_service.enqueue = AsyncMock(
            return_value=MagicMock(success=True, should_start=False, track=resolved, position=2)
        )
        cog = _make_cog(container)
        cog._start_long_track_vote = AsyncMock(return_value=False)
        cog._send_now_playing = AsyncMock()
        cog._send_queued = AsyncMock()
        await cog._play_track(interaction, "any")
        cog._send_queued.assert_awaited_once()
        cog._send_now_playing.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_swallows_exception(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.audio_resolver.resolve = AsyncMock(side_effect=RuntimeError("boom"))
        cog = _make_cog(container)
        cog.logger = MagicMock()
        await cog._play_track(interaction, "any")
        msg = interaction.followup.send.call_args.args[0]
        assert "Command failed" in msg


# =============================================================================
# _start_long_track_vote
# =============================================================================


class TestStartLongTrackVote:
    @pytest.mark.asyncio
    async def test_short_track_returns_false(self):
        member, interaction = _interaction_in_voice()
        cog = _make_cog()
        result = await cog._start_long_track_vote(
            interaction,
            Track(
                id=TrackId(value="x"),
                title="Short",
                webpage_url="https://yt/x",
                duration_seconds=60,
            ),
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_no_duration_returns_false(self):
        member, interaction = _interaction_in_voice()
        cog = _make_cog()
        result = await cog._start_long_track_vote(
            interaction,
            Track(
                id=TrackId(value="x"),
                title="Unknown",
                webpage_url="https://yt/x",
                duration_seconds=None,
            ),
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_few_listeners_returns_false(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.voice_adapter.get_listeners = AsyncMock(return_value=[1])
        cog = _make_cog(container)
        long_track = Track(
            id=TrackId(value="lt"),
            title="Long",
            webpage_url="https://yt/lt",
            duration_seconds=3600,  # very long
        )
        result = await cog._start_long_track_vote(interaction, long_track)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_channel_id_returns_true_with_error(self):
        member, interaction = _interaction_in_voice()
        interaction.channel_id = None
        container = _container()
        container.voice_adapter.get_listeners = AsyncMock(return_value=[1, 2, 3, 4, 5, 6, 7, 8])
        cog = _make_cog(container)
        long_track = Track(
            id=TrackId(value="lt"),
            title="Long",
            webpage_url="https://yt/lt",
            duration_seconds=3600,
        )
        result = await cog._start_long_track_vote(interaction, long_track)
        assert result is True
        msg = interaction.followup.send.call_args.args[0]
        assert "no channel context" in msg.lower()

    @pytest.mark.asyncio
    async def test_starts_vote_when_channel_messageable(self):
        member, interaction = _interaction_in_voice()
        interaction.channel_id = 555
        container = _container()
        container.voice_adapter.get_listeners = AsyncMock(return_value=[1, 2, 3, 4, 5, 6, 7, 8])
        bot = MagicMock()
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock(return_value=MagicMock())
        bot.get_channel = MagicMock(return_value=channel)
        cog = _make_cog(container, bot=bot)
        long_track = Track(
            id=TrackId(value="lt"),
            title="Long",
            webpage_url="https://yt/lt",
            duration_seconds=3600,
        )
        result = await cog._start_long_track_vote(interaction, long_track)
        assert result is True
        channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_messageable_channel_returns_true_with_error(self):
        member, interaction = _interaction_in_voice()
        interaction.channel_id = 555
        container = _container()
        container.voice_adapter.get_listeners = AsyncMock(return_value=[1, 2, 3, 4, 5, 6, 7, 8])
        bot = MagicMock()
        bot.get_channel = MagicMock(return_value=object())  # not Messageable
        cog = _make_cog(container, bot=bot)
        long_track = Track(
            id=TrackId(value="lt"),
            title="Long",
            webpage_url="https://yt/lt",
            duration_seconds=3600,
        )
        result = await cog._start_long_track_vote(interaction, long_track)
        assert result is True
        msg = interaction.followup.send.call_args.args[0]
        assert "Could not find a channel" in msg


# =============================================================================
# _handle_playlist + _auto_enqueue_youtube_playlist
# =============================================================================


class TestHandlePlaylist:
    @pytest.mark.asyncio
    async def test_empty_preview_message(self):
        from discord_music_player.domain.music.entities import PlaylistPreview

        member, interaction = _interaction_in_voice()
        container = _container()
        container.audio_resolver.preview_playlist = AsyncMock(
            return_value=PlaylistPreview(entries=[], title="Empty")
        )
        cog = _make_cog(container)
        await cog._handle_playlist(interaction, "https://yt/pl")
        msg = interaction.followup.send.call_args.args[0]
        assert "empty" in msg.lower()

    @pytest.mark.asyncio
    async def test_auto_enqueue_route_when_count_specified(self):
        from discord_music_player.domain.music.entities import PlaylistEntry, PlaylistPreview

        member, interaction = _interaction_in_voice()
        container = _container()
        container.audio_resolver.preview_playlist = AsyncMock(
            return_value=PlaylistPreview(
                entries=[
                    PlaylistEntry(title=f"E{i}", url=f"https://yt/e{i}") for i in range(5)
                ],
                title="My Playlist",
            )
        )
        cog = _make_cog(container)
        cog._auto_enqueue_youtube_playlist = AsyncMock()
        await cog._handle_playlist(interaction, "https://yt/pl", count=3)
        cog._auto_enqueue_youtube_playlist.assert_awaited_once()


class TestAutoEnqueueYouTubePlaylist:
    @pytest.mark.asyncio
    async def test_empty_selection_warns_about_start_offset(self):
        from discord_music_player.domain.music.entities import PlaylistEntry, PlaylistPreview

        member, interaction = _interaction_in_voice()
        container = _container()
        cog = _make_cog(container)
        # Use a real-ish preview but force start past the end
        preview = PlaylistPreview(
            entries=[PlaylistEntry(title="E", url="https://yt/e")],
            title="Pl",
        )
        await cog._auto_enqueue_youtube_playlist(
            interaction, preview=preview, count=None, start=999, shuffle=False
        )
        # Either a response or ephemeral via guard — find the call
        if interaction.response.send_message.called:
            sent = interaction.response.send_message.call_args.args[0]
        else:
            sent = interaction.followup.send.call_args.args[0]
        assert "past the end" in sent

    @pytest.mark.asyncio
    async def test_success_routes_to_finalize_playlist_import(self):
        from discord_music_player.domain.music.entities import PlaylistEntry, PlaylistPreview

        member, interaction = _interaction_in_voice()
        container = _container()
        cog = _make_cog(container)
        cog._finalize_playlist_import = AsyncMock()

        preview = PlaylistPreview(
            entries=[
                PlaylistEntry(title=f"E{i}", url=f"https://yt/e{i}") for i in range(3)
            ],
            title="Mix",
        )
        await cog._auto_enqueue_youtube_playlist(
            interaction, preview=preview, count=2, start=1, shuffle=False
        )
        cog._finalize_playlist_import.assert_awaited_once()


# =============================================================================
# _finalize_playlist_import
# =============================================================================


class TestFinalizePlaylistImport:
    @pytest.mark.asyncio
    async def test_no_resolved_tracks(self):
        member, interaction = _interaction_in_voice()
        container = _container()
        container.audio_resolver.resolve_many = AsyncMock(return_value=[])
        cog = _make_cog(container)
        await cog._finalize_playlist_import(
            interaction,
            resolver_queries=["https://yt/a", "https://yt/b"],
            source_label="Test",
            suggested_name="test",
        )
        msg = interaction.followup.send.call_args.args[0]
        assert "Couldn't resolve" in msg

    @pytest.mark.asyncio
    async def test_zero_enqueued_skips_save_prompt(self):
        member, interaction = _interaction_in_voice()
        tracks = [_track("a"), _track("b")]
        container = _container()
        container.audio_resolver.resolve_many = AsyncMock(return_value=tracks)
        cog = _make_cog(container)
        cog.enqueue_and_start = AsyncMock(return_value=MagicMock(enqueued=0))
        await cog._finalize_playlist_import(
            interaction,
            resolver_queries=["https://yt/a", "https://yt/b"],
            source_label="Test",
            suggested_name="test",
        )
        # Two followup.send calls: status, "Queued 0/2"; no save-prompt
        assert interaction.followup.send.await_count == 1

    @pytest.mark.asyncio
    async def test_partial_enqueue_shows_save_prompt(self):
        member, interaction = _interaction_in_voice()
        tracks = [_track("a"), _track("b"), _track("c")]
        container = _container()
        container.audio_resolver.resolve_many = AsyncMock(return_value=tracks)
        cog = _make_cog(container)
        cog.enqueue_and_start = AsyncMock(return_value=MagicMock(enqueued=2))
        sent = MagicMock()
        interaction.followup.send = AsyncMock(return_value=sent)
        await cog._finalize_playlist_import(
            interaction,
            resolver_queries=["https://yt/a", "https://yt/b", "https://yt/c"],
            source_label="Test",
            suggested_name="test-pl",
        )
        # Two followups: confirmation + save prompt
        assert interaction.followup.send.await_count == 2


# =============================================================================
# _send_queued
# =============================================================================


class TestSendQueued:
    @pytest.mark.asyncio
    async def test_sends_queued_message_and_tracks(self):
        member, interaction = _interaction_in_voice()
        interaction.channel_id = 555
        container = _container()
        msm = container.message_state_manager
        msm.track_queued = MagicMock()
        msm.update_next_up = AsyncMock()

        sent = MagicMock()
        sent.id = 9001
        sent.delete = AsyncMock()
        interaction.followup.send = AsyncMock(return_value=sent)

        # Session that exposes peek
        session = MagicMock()
        session.peek = MagicMock(return_value=None)
        container.session_repository.get = AsyncMock(return_value=session)

        cog = _make_cog(container)
        await cog._send_queued(interaction, _track("q"))

        msm.track_queued.assert_called_once()
        msm.update_next_up.assert_awaited_once()


# =============================================================================
# extract_listening_query — Spotify + Apple Music + nothing
# =============================================================================


class TestExtractListeningQuery:
    def test_returns_none_for_user_without_member_attrs(self):
        # discord.User has no .activities, treated as no-activity
        user = MagicMock(spec=discord.User)
        assert extract_listening_query(user) is None

    def test_returns_none_for_member_with_no_activities(self):
        member = MagicMock(spec=discord.Member)
        member.activities = []
        assert extract_listening_query(member) is None

    def test_extracts_from_spotify_typed_activity(self):
        spotify = MagicMock(spec=discord.Spotify)
        spotify.title = "Song Title"
        spotify.artist = "Artist Name"

        member = MagicMock(spec=discord.Member)
        member.activities = [spotify]

        assert extract_listening_query(member) == "Artist Name - Song Title"

    def test_extracts_from_apple_music_generic_activity_by_app_id(self):
        apple = MagicMock(spec=discord.Activity)
        apple.type = discord.ActivityType.listening
        apple.application_id = APPLE_MUSIC_APP_ID
        apple.name = "Apple Music"
        apple.details = "Spent A Quarter Ticket (Intro)"
        apple.state = "Bally Baby & Hoodrich Keem"

        member = MagicMock(spec=discord.Member)
        member.activities = [apple]

        assert (
            extract_listening_query(member)
            == "Bally Baby & Hoodrich Keem - Spent A Quarter Ticket (Intro)"
        )

    def test_extracts_apple_music_when_app_id_missing_but_name_matches(self):
        # app_id can be None for some integrations — fall back to name match
        apple = MagicMock(spec=discord.Activity)
        apple.type = discord.ActivityType.listening
        apple.application_id = None
        apple.name = "Apple Music"
        apple.details = "Track"
        apple.state = "Artist"

        member = MagicMock(spec=discord.Member)
        member.activities = [apple]

        assert extract_listening_query(member) == "Artist - Track"

    def test_skips_non_listening_activities(self):
        playing = MagicMock(spec=discord.Activity)
        playing.type = discord.ActivityType.playing
        playing.application_id = APPLE_MUSIC_APP_ID
        playing.name = "Apple Music"
        playing.details = "Track"
        playing.state = "Artist"

        member = MagicMock(spec=discord.Member)
        member.activities = [playing]

        assert extract_listening_query(member) is None

    def test_skips_listening_activity_from_other_apps(self):
        other = MagicMock(spec=discord.Activity)
        other.type = discord.ActivityType.listening
        other.application_id = 9999
        other.name = "SomeOtherMusicApp"
        other.details = "Track"
        other.state = "Artist"

        member = MagicMock(spec=discord.Member)
        member.activities = [other]

        assert extract_listening_query(member) is None

    def test_picks_first_recognised_among_many(self):
        custom = MagicMock(spec=discord.CustomActivity)
        spotify = MagicMock(spec=discord.Spotify)
        spotify.title = "Spot Title"
        spotify.artist = "Spot Artist"

        member = MagicMock(spec=discord.Member)
        member.activities = [custom, spotify]

        assert extract_listening_query(member) == "Spot Artist - Spot Title"
