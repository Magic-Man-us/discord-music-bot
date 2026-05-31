"""Tests for FollowMode — queue-behind live mirror with a dwell gate."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_music_player.application.services.follow_mode import FollowMode
from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.domain.shared.constants import LimitConstants, TimeConstants
from discord_music_player.domain.shared.events import (
    FollowModeStopped,
    VoiceMemberLeftVoiceChannel,
    get_event_bus,
    reset_event_bus,
)

GUILD_ID = 111111111
USER_ID = 222222222
OTHER_USER_ID = 333333333
USER_NAME = "Tester"


@pytest.fixture(autouse=True)
def _isolate_event_bus():
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture(autouse=True)
def _instant_dwell(monkeypatch: pytest.MonkeyPatch):
    """Make the dwell gate fire immediately so timer tests are deterministic."""
    monkeypatch.setattr(TimeConstants, "FOLLOW_DWELL_SECONDS", 0)


def _track(track_id: str = "abc", title: str = "T") -> Track:
    return Track(
        id=TrackId(value=track_id),
        title=title,
        webpage_url=f"https://yt/{track_id}",
        duration_seconds=180,
    )


@pytest.fixture
def audio_resolver() -> MagicMock:
    r = MagicMock()
    r.resolve = AsyncMock(return_value=_track())
    return r


@pytest.fixture
def queue_service() -> MagicMock:
    qs = MagicMock()
    qs.enqueue = AsyncMock(
        return_value=MagicMock(
            success=True, should_start=False, message="ok", track=_track()
        )
    )
    return qs


@pytest.fixture
def playback_service() -> MagicMock:
    ps = MagicMock()
    ps.start_playback = AsyncMock()
    return ps


@pytest.fixture
def follow_mode(
    audio_resolver: MagicMock,
    queue_service: MagicMock,
    playback_service: MagicMock,
) -> FollowMode:
    return FollowMode(
        audio_resolver=audio_resolver,
        queue_service=queue_service,
        playback_service=playback_service,
    )


# ============================================================================
# Lifecycle
# ============================================================================


class TestLifecycle:
    def test_default_state_is_disabled(self, follow_mode: FollowMode) -> None:
        assert follow_mode.is_enabled(GUILD_ID) is False
        assert follow_mode.followed_user_id(GUILD_ID) is None

    def test_enable_marks_state(self, follow_mode: FollowMode) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        assert follow_mode.is_enabled(GUILD_ID) is True
        assert follow_mode.followed_user_id(GUILD_ID) == USER_ID

    def test_enable_defaults_to_max_follow_tracks(
        self, follow_mode: FollowMode
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        assert (
            follow_mode._states[GUILD_ID].max_tracks == LimitConstants.MAX_FOLLOW_TRACKS
        )

    def test_enable_accepts_custom_max_tracks(self, follow_mode: FollowMode) -> None:
        follow_mode.enable(
            guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME, max_tracks=3
        )
        assert follow_mode._states[GUILD_ID].max_tracks == 3

    def test_enable_can_prime_last_key_and_count(self, follow_mode: FollowMode) -> None:
        follow_mode.enable(
            guild_id=GUILD_ID,
            user_id=USER_ID,
            user_name=USER_NAME,
            last_enqueued_key="Artist - Track",
            enqueued_count=1,
        )
        state = follow_mode._states[GUILD_ID]
        assert state.last_enqueued_key == "Artist - Track"
        assert state.enqueued_count == 1

    def test_disable_clears_state(self, follow_mode: FollowMode) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        follow_mode.disable(GUILD_ID)
        assert follow_mode.is_enabled(GUILD_ID) is False

    def test_enable_replaces_previous_followed_user(
        self, follow_mode: FollowMode
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name="A")
        follow_mode.enable(guild_id=GUILD_ID, user_id=OTHER_USER_ID, user_name="B")
        assert follow_mode.followed_user_id(GUILD_ID) == OTHER_USER_ID

    def test_start_subscribes_to_member_left(self, follow_mode: FollowMode) -> None:
        bus = get_event_bus()
        follow_mode.start()
        assert follow_mode._on_member_left in bus._handlers.get(
            VoiceMemberLeftVoiceChannel, []
        )
        follow_mode.stop()

    def test_stop_unsubscribes_and_clears(self, follow_mode: FollowMode) -> None:
        bus = get_event_bus()
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        follow_mode.start()
        follow_mode.stop()
        assert follow_mode._on_member_left not in bus._handlers.get(
            VoiceMemberLeftVoiceChannel, []
        )
        assert follow_mode.is_enabled(GUILD_ID) is False


# ============================================================================
# seed_current — the immediate, ungated /playmine starting song
# ============================================================================


class TestSeedCurrent:
    @pytest.mark.asyncio
    async def test_no_op_when_guild_not_followed(
        self, follow_mode: FollowMode, queue_service: MagicMock
    ) -> None:
        result = await follow_mode.seed_current(GUILD_ID, USER_ID, "Artist - Track")
        assert result is False
        queue_service.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enqueues_and_starts_when_idle(
        self,
        follow_mode: FollowMode,
        queue_service: MagicMock,
        playback_service: MagicMock,
    ) -> None:
        queue_service.enqueue = AsyncMock(
            return_value=MagicMock(success=True, should_start=True, track=_track())
        )
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)

        result = await follow_mode.seed_current(GUILD_ID, USER_ID, "Artist - Track")

        assert result is True
        queue_service.enqueue.assert_awaited_once()
        playback_service.start_playback.assert_awaited_once_with(GUILD_ID)
        assert follow_mode._states[GUILD_ID].last_enqueued_key == "Artist - Track"

    @pytest.mark.asyncio
    async def test_dedup_when_same_as_last_enqueued(
        self, follow_mode: FollowMode, queue_service: MagicMock
    ) -> None:
        follow_mode.enable(
            guild_id=GUILD_ID,
            user_id=USER_ID,
            user_name=USER_NAME,
            last_enqueued_key="Artist - Track",
        )
        result = await follow_mode.seed_current(GUILD_ID, USER_ID, "Artist - Track")
        assert result is False
        queue_service.enqueue.assert_not_awaited()


# ============================================================================
# on_track_change — dwell gate (debounce), no immediate enqueue
# ============================================================================


class TestDwellGate:
    @pytest.mark.asyncio
    async def test_no_op_when_event_user_is_not_followed(
        self, follow_mode: FollowMode, queue_service: MagicMock
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        armed = await follow_mode.on_track_change(GUILD_ID, OTHER_USER_ID, "A - T")
        assert armed is False
        assert GUILD_ID not in follow_mode._dwell_timers

    @pytest.mark.asyncio
    async def test_new_song_arms_dwell_timer_without_enqueueing(
        self, follow_mode: FollowMode, queue_service: MagicMock
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        armed = await follow_mode.on_track_change(GUILD_ID, USER_ID, "A - T")
        assert armed is True
        assert GUILD_ID in follow_mode._dwell_timers
        # Nothing queued at arm time — only after the gate elapses.
        follow_mode._cancel_dwell_timer(GUILD_ID)
        queue_service.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dedup_against_last_enqueued(self, follow_mode: FollowMode) -> None:
        follow_mode.enable(
            guild_id=GUILD_ID,
            user_id=USER_ID,
            user_name=USER_NAME,
            last_enqueued_key="A - T",
        )
        armed = await follow_mode.on_track_change(GUILD_ID, USER_ID, "A - T")
        assert armed is False
        assert GUILD_ID not in follow_mode._dwell_timers

    @pytest.mark.asyncio
    async def test_same_pending_song_does_not_restart_timer(
        self, follow_mode: FollowMode
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        await follow_mode.on_track_change(GUILD_ID, USER_ID, "A - T")
        first = follow_mode._dwell_timers[GUILD_ID]
        armed = await follow_mode.on_track_change(GUILD_ID, USER_ID, "A - T")
        assert armed is False
        assert follow_mode._dwell_timers[GUILD_ID] is first
        follow_mode._cancel_dwell_timer(GUILD_ID)

    @pytest.mark.asyncio
    async def test_dwell_commit_appends_track(
        self,
        follow_mode: FollowMode,
        queue_service: MagicMock,
        playback_service: MagicMock,
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        follow_mode._states[GUILD_ID].pending_key = "A - T"

        await follow_mode._dwell_then_enqueue(GUILD_ID, "A - T")

        queue_service.enqueue.assert_awaited_once()
        # should_start=False (something playing) → appended, NOT started.
        playback_service.start_playback.assert_not_awaited()
        state = follow_mode._states[GUILD_ID]
        assert state.last_enqueued_key == "A - T"
        assert state.pending_key is None
        assert state.enqueued_count == 1

    @pytest.mark.asyncio
    async def test_dwell_commit_notifies_when_track_becomes_next_up(
        self, follow_mode: FollowMode, queue_service: MagicMock
    ) -> None:
        next_track = _track("next", "Next Song")
        queue_service.enqueue = AsyncMock(
            return_value=MagicMock(
                success=True,
                should_start=False,
                position=0,
                track=next_track,
                message="ok",
            )
        )
        callback = AsyncMock()
        follow_mode.set_next_track_queued_callback(callback)
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        follow_mode._states[GUILD_ID].pending_key = "A - T"

        await follow_mode._dwell_then_enqueue(GUILD_ID, "A - T")

        callback.assert_awaited_once_with(GUILD_ID, next_track)

    @pytest.mark.asyncio
    async def test_dwell_commit_does_not_notify_when_added_later_in_queue(
        self, follow_mode: FollowMode, queue_service: MagicMock
    ) -> None:
        queue_service.enqueue = AsyncMock(
            return_value=MagicMock(
                success=True,
                should_start=False,
                position=2,
                track=_track("later", "Later Song"),
                message="ok",
            )
        )
        callback = AsyncMock()
        follow_mode.set_next_track_queued_callback(callback)
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        follow_mode._states[GUILD_ID].pending_key = "A - T"

        await follow_mode._dwell_then_enqueue(GUILD_ID, "A - T")

        callback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dwell_commit_skipped_when_superseded(
        self, follow_mode: FollowMode, queue_service: MagicMock
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        follow_mode._states[GUILD_ID].pending_key = "newer song"

        # The timer that fires is for an older candidate the user skipped past.
        await follow_mode._dwell_then_enqueue(GUILD_ID, "older song")

        queue_service.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resolve_failure_keeps_following(
        self,
        follow_mode: FollowMode,
        audio_resolver: MagicMock,
        queue_service: MagicMock,
    ) -> None:
        audio_resolver.resolve = AsyncMock(return_value=None)
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        follow_mode._states[GUILD_ID].pending_key = "Bogus - Query"

        await follow_mode._dwell_then_enqueue(GUILD_ID, "Bogus - Query")

        queue_service.enqueue.assert_not_awaited()
        assert follow_mode.is_enabled(GUILD_ID) is True

    @pytest.mark.asyncio
    async def test_auto_disables_after_cap(self, follow_mode: FollowMode) -> None:
        follow_mode.enable(
            guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME, max_tracks=2
        )
        await follow_mode.seed_current(GUILD_ID, USER_ID, "A - 1")
        assert follow_mode.is_enabled(GUILD_ID) is True

        follow_mode._states[GUILD_ID].pending_key = "A - 2"
        await follow_mode._dwell_then_enqueue(GUILD_ID, "A - 2")
        assert follow_mode.is_enabled(GUILD_ID) is False


# ============================================================================
# Stop detection — activity cleared → grace timer → disconnect
# ============================================================================


class TestStopDetection:
    @pytest.mark.asyncio
    async def test_activity_cleared_arms_grace_and_cancels_dwell(
        self, follow_mode: FollowMode
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        await follow_mode.on_track_change(GUILD_ID, USER_ID, "A - T")
        assert GUILD_ID in follow_mode._dwell_timers

        await follow_mode.on_activity_cleared(GUILD_ID, USER_ID)

        assert GUILD_ID not in follow_mode._dwell_timers
        assert GUILD_ID in follow_mode._idle_timers
        assert follow_mode._states[GUILD_ID].pending_key is None
        follow_mode._cancel_idle_timer(GUILD_ID)

    @pytest.mark.asyncio
    async def test_activity_cleared_ignored_for_other_user(
        self, follow_mode: FollowMode
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        await follow_mode.on_activity_cleared(GUILD_ID, OTHER_USER_ID)
        assert GUILD_ID not in follow_mode._idle_timers

    @pytest.mark.asyncio
    async def test_track_change_cancels_pending_grace_timer(
        self, follow_mode: FollowMode
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        await follow_mode.on_activity_cleared(GUILD_ID, USER_ID)
        assert GUILD_ID in follow_mode._idle_timers

        await follow_mode.on_track_change(GUILD_ID, USER_ID, "A - T")

        assert GUILD_ID not in follow_mode._idle_timers
        follow_mode._cancel_dwell_timer(GUILD_ID)

    @pytest.mark.asyncio
    async def test_grace_expiry_disconnects_and_publishes(
        self, follow_mode: FollowMode, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(TimeConstants, "FOLLOW_STOP_GRACE_SECONDS", 0)
        seen: list[FollowModeStopped] = []

        async def _capture(event: FollowModeStopped) -> None:
            seen.append(event)

        get_event_bus().subscribe(FollowModeStopped, _capture)

        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        await follow_mode._grace_then_disconnect(GUILD_ID)

        assert follow_mode.is_enabled(GUILD_ID) is False
        assert len(seen) == 1
        assert seen[0].guild_id == GUILD_ID

    @pytest.mark.asyncio
    async def test_disable_cancels_timers(self, follow_mode: FollowMode) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        await follow_mode.on_track_change(GUILD_ID, USER_ID, "A - T")
        await follow_mode.on_activity_cleared(GUILD_ID, USER_ID)
        follow_mode.disable(GUILD_ID)
        assert GUILD_ID not in follow_mode._dwell_timers
        assert GUILD_ID not in follow_mode._idle_timers


# ============================================================================
# Auto-disable on member-left-VC event
# ============================================================================


class TestMemberLeftAutoDisable:
    @pytest.mark.asyncio
    async def test_disables_when_followed_user_leaves(
        self, follow_mode: FollowMode
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        event = VoiceMemberLeftVoiceChannel(
            guild_id=GUILD_ID, channel_id=999, user_id=USER_ID
        )
        await follow_mode._on_member_left(event)
        assert follow_mode.is_enabled(GUILD_ID) is False

    @pytest.mark.asyncio
    async def test_ignores_when_other_user_leaves(
        self, follow_mode: FollowMode
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        event = VoiceMemberLeftVoiceChannel(
            guild_id=GUILD_ID, channel_id=999, user_id=OTHER_USER_ID
        )
        await follow_mode._on_member_left(event)
        assert follow_mode.is_enabled(GUILD_ID) is True

    @pytest.mark.asyncio
    async def test_ignores_when_not_following_in_that_guild(
        self, follow_mode: FollowMode
    ) -> None:
        event = VoiceMemberLeftVoiceChannel(
            guild_id=GUILD_ID, channel_id=999, user_id=USER_ID
        )
        await follow_mode._on_member_left(event)  # should not raise
        assert follow_mode.is_enabled(GUILD_ID) is False
