"""Tests for FollowMode — live music-activity mirror for /dj follow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_music_player.application.services.follow_mode import FollowMode
from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.domain.shared.constants import LimitConstants
from discord_music_player.domain.shared.events import (
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
        return_value=MagicMock(success=True, should_start=False, message="ok", track=_track())
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

    def test_disable_clears_state(self, follow_mode: FollowMode) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        follow_mode.disable(GUILD_ID)
        assert follow_mode.is_enabled(GUILD_ID) is False

    def test_enable_replaces_previous_followed_user(self, follow_mode: FollowMode) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name="A")
        follow_mode.enable(guild_id=GUILD_ID, user_id=OTHER_USER_ID, user_name="B")
        assert follow_mode.followed_user_id(GUILD_ID) == OTHER_USER_ID

    def test_start_subscribes_to_member_left(self, follow_mode: FollowMode) -> None:
        bus = get_event_bus()
        follow_mode.start()
        assert follow_mode._on_member_left in bus._handlers.get(VoiceMemberLeftVoiceChannel, [])
        follow_mode.stop()

    def test_stop_unsubscribes_and_clears(self, follow_mode: FollowMode) -> None:
        bus = get_event_bus()
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        follow_mode.start()
        follow_mode.stop()
        assert follow_mode._on_member_left not in bus._handlers.get(VoiceMemberLeftVoiceChannel, [])
        assert follow_mode.is_enabled(GUILD_ID) is False


# ============================================================================
# on_track_change — dedup + cap + enqueue
# ============================================================================


class TestOnTrackChange:
    @pytest.mark.asyncio
    async def test_no_op_when_guild_not_followed(
        self, follow_mode: FollowMode, queue_service: MagicMock
    ) -> None:
        result = await follow_mode.on_track_change(
            guild_id=GUILD_ID, user_id=USER_ID, query="Artist - Track"
        )
        assert result is False
        queue_service.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_op_when_event_user_is_not_followed(
        self, follow_mode: FollowMode, queue_service: MagicMock
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        result = await follow_mode.on_track_change(
            guild_id=GUILD_ID, user_id=OTHER_USER_ID, query="Artist - Track"
        )
        assert result is False
        queue_service.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enqueues_on_new_track(
        self, follow_mode: FollowMode, queue_service: MagicMock
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        result = await follow_mode.on_track_change(
            guild_id=GUILD_ID, user_id=USER_ID, query="Artist - Track"
        )
        assert result is True
        queue_service.enqueue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dedup_skips_repeat_of_same_query(
        self, follow_mode: FollowMode, queue_service: MagicMock
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        await follow_mode.on_track_change(
            guild_id=GUILD_ID, user_id=USER_ID, query="Artist - Track"
        )
        result = await follow_mode.on_track_change(
            guild_id=GUILD_ID, user_id=USER_ID, query="Artist - Track"
        )
        assert result is False
        # enqueue called only for the first one
        assert queue_service.enqueue.await_count == 1

    @pytest.mark.asyncio
    async def test_starts_playback_when_should_start(
        self, follow_mode: FollowMode, queue_service: MagicMock, playback_service: MagicMock
    ) -> None:
        queue_service.enqueue = AsyncMock(
            return_value=MagicMock(
                success=True, should_start=True, message="now playing", track=_track()
            )
        )
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        await follow_mode.on_track_change(
            guild_id=GUILD_ID, user_id=USER_ID, query="A - T"
        )
        playback_service.start_playback.assert_awaited_once_with(GUILD_ID)

    @pytest.mark.asyncio
    async def test_resolve_failure_returns_false_and_keeps_following(
        self, follow_mode: FollowMode, audio_resolver: MagicMock, queue_service: MagicMock
    ) -> None:
        audio_resolver.resolve = AsyncMock(return_value=None)
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        result = await follow_mode.on_track_change(
            guild_id=GUILD_ID, user_id=USER_ID, query="Bogus - Query"
        )
        assert result is False
        queue_service.enqueue.assert_not_awaited()
        # state preserved → next valid track will still enqueue
        assert follow_mode.is_enabled(GUILD_ID) is True

    @pytest.mark.asyncio
    async def test_enqueue_rejection_does_not_count_toward_cap(
        self, follow_mode: FollowMode, queue_service: MagicMock
    ) -> None:
        queue_service.enqueue = AsyncMock(
            return_value=MagicMock(
                success=False, should_start=False, message="queue full", track=None
            )
        )
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        result = await follow_mode.on_track_change(
            guild_id=GUILD_ID, user_id=USER_ID, query="A - T"
        )
        assert result is False
        # still enabled, count untouched
        assert follow_mode.is_enabled(GUILD_ID) is True
        assert follow_mode._states[GUILD_ID].enqueued_count == 0

    @pytest.mark.asyncio
    async def test_auto_disables_after_cap(
        self, follow_mode: FollowMode
    ) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        for i in range(LimitConstants.MAX_FOLLOW_TRACKS):
            await follow_mode.on_track_change(
                guild_id=GUILD_ID, user_id=USER_ID, query=f"Artist - Track{i}"
            )
        assert follow_mode.is_enabled(GUILD_ID) is False


# ============================================================================
# Auto-disable on member-left-VC event
# ============================================================================


class TestMemberLeftAutoDisable:
    @pytest.mark.asyncio
    async def test_disables_when_followed_user_leaves(self, follow_mode: FollowMode) -> None:
        follow_mode.enable(guild_id=GUILD_ID, user_id=USER_ID, user_name=USER_NAME)
        event = VoiceMemberLeftVoiceChannel(
            guild_id=GUILD_ID, channel_id=999, user_id=USER_ID
        )
        await follow_mode._on_member_left(event)
        assert follow_mode.is_enabled(GUILD_ID) is False

    @pytest.mark.asyncio
    async def test_ignores_when_other_user_leaves(self, follow_mode: FollowMode) -> None:
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
