"""Tests for AutoDJ — event-driven idle detection that auto-enables radio."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from discord_music_player.application.services.auto_dj import AutoDJ
from discord_music_player.application.services.radio_models import RadioToggleResult
from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.domain.shared.events import (
    QueueExhausted,
    TrackStartedPlaying,
    get_event_bus,
    reset_event_bus,
)

# ============================================================================
# Fixtures
# ============================================================================

GUILD_ID = 111111111


@pytest.fixture(autouse=True)
def _isolate_event_bus():
    """Reset the global event bus before and after each test to prevent leakage."""
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture
def seed_track() -> Track:
    return Track(
        id=TrackId(value="seed-1"),
        title="Seed Song",
        webpage_url="https://youtube.com/watch?v=seed1",
        duration_seconds=200,
        artist="Seed Artist",
        requested_by_id=42,
        requested_by_name="Alice",
    )


@pytest.fixture
def empty_session() -> GuildPlaybackSession:
    """Session with no tracks — idle state."""
    return GuildPlaybackSession(guild_id=GUILD_ID)


@pytest.fixture
def radio_service() -> MagicMock:
    svc = MagicMock()
    svc.is_enabled = MagicMock(return_value=False)
    svc.toggle_radio = AsyncMock(
        return_value=RadioToggleResult(
            enabled=True,
            tracks_added=3,
            message="Radio enabled.",
        )
    )
    return svc


@pytest.fixture
def playback_service() -> MagicMock:
    svc = MagicMock()
    svc.start_playback = AsyncMock()
    return svc


@pytest.fixture
def session_repo(empty_session: GuildPlaybackSession) -> MagicMock:
    repo = MagicMock()
    repo.get = AsyncMock(return_value=empty_session)
    repo.save = AsyncMock()
    return repo


@pytest.fixture
def history_repo(seed_track: Track) -> MagicMock:
    repo = MagicMock()
    repo.get_recent = AsyncMock(return_value=[seed_track])
    return repo


@pytest.fixture
def ai_client() -> MagicMock:
    client = MagicMock()
    client.is_available = AsyncMock(return_value=True)
    return client


@pytest.fixture
def auto_dj(
    radio_service: MagicMock,
    playback_service: MagicMock,
    session_repo: MagicMock,
    history_repo: MagicMock,
    ai_client: MagicMock,
) -> AutoDJ:
    return AutoDJ(
        radio_service=radio_service,
        playback_service=playback_service,
        session_repository=session_repo,
        history_repository=history_repo,
        ai_client=ai_client,
    )


# ============================================================================
# Start / Stop Lifecycle
# ============================================================================


class TestLifecycle:
    def test_start_subscribes_to_events(self, auto_dj: AutoDJ) -> None:
        bus = get_event_bus()
        auto_dj.start()

        assert auto_dj._started is True
        assert auto_dj._on_queue_exhausted in bus._handlers.get(QueueExhausted, [])
        assert auto_dj._on_track_started in bus._handlers.get(TrackStartedPlaying, [])

        auto_dj.stop()

    def test_start_is_idempotent(self, auto_dj: AutoDJ) -> None:
        auto_dj.start()
        auto_dj.start()  # second call should be no-op
        assert auto_dj._started is True
        auto_dj.stop()

    def test_stop_unsubscribes_and_clears_timers(self, auto_dj: AutoDJ) -> None:
        bus = get_event_bus()
        auto_dj.start()
        auto_dj.stop()

        assert auto_dj._started is False
        assert auto_dj._timers == {}
        assert auto_dj._on_queue_exhausted not in bus._handlers.get(QueueExhausted, [])

    def test_stop_cancels_pending_timers(self, auto_dj: AutoDJ) -> None:
        auto_dj.start()
        # Manually inject a fake pending timer
        fake_task = MagicMock()
        fake_task.done.return_value = False
        auto_dj._timers[GUILD_ID] = fake_task

        auto_dj.stop()

        fake_task.cancel.assert_called_once()
        assert auto_dj._timers == {}

    def test_stop_without_start_is_noop(self, auto_dj: AutoDJ) -> None:
        auto_dj.stop()  # should not raise
        assert auto_dj._started is False


# ============================================================================
# Opt-in (enable / disable / is_enabled)
# ============================================================================


class TestOptIn:
    def test_default_state_is_disabled(self, auto_dj: AutoDJ) -> None:
        assert auto_dj.is_enabled(GUILD_ID) is False

    def test_enable_marks_guild_as_enabled(self, auto_dj: AutoDJ) -> None:
        auto_dj.enable(GUILD_ID)
        assert auto_dj.is_enabled(GUILD_ID) is True

    def test_enable_is_idempotent(self, auto_dj: AutoDJ) -> None:
        auto_dj.enable(GUILD_ID)
        auto_dj.enable(GUILD_ID)
        assert auto_dj.is_enabled(GUILD_ID) is True

    def test_disable_clears_flag(self, auto_dj: AutoDJ) -> None:
        auto_dj.enable(GUILD_ID)
        auto_dj.disable(GUILD_ID)
        assert auto_dj.is_enabled(GUILD_ID) is False

    def test_disable_when_not_enabled_is_noop(self, auto_dj: AutoDJ) -> None:
        auto_dj.disable(GUILD_ID)  # should not raise
        assert auto_dj.is_enabled(GUILD_ID) is False

    def test_disable_cancels_pending_timer(self, auto_dj: AutoDJ) -> None:
        auto_dj.enable(GUILD_ID)
        fake_task = MagicMock()
        fake_task.done.return_value = False
        auto_dj._timers[GUILD_ID] = fake_task

        auto_dj.disable(GUILD_ID)

        fake_task.cancel.assert_called_once()
        assert GUILD_ID not in auto_dj._timers

    def test_enable_is_per_guild(self, auto_dj: AutoDJ) -> None:
        auto_dj.enable(111)
        assert auto_dj.is_enabled(111) is True
        assert auto_dj.is_enabled(222) is False

    def test_stop_clears_all_enabled_guilds(self, auto_dj: AutoDJ) -> None:
        auto_dj.start()
        auto_dj.enable(111)
        auto_dj.enable(222)

        auto_dj.stop()

        assert auto_dj.is_enabled(111) is False
        assert auto_dj.is_enabled(222) is False


# ============================================================================
# Queue Exhausted → Timer Scheduling
# ============================================================================


class TestOnQueueExhausted:
    @pytest.mark.asyncio
    async def test_schedules_timer_on_queue_exhausted(self, auto_dj: AutoDJ) -> None:
        event = QueueExhausted(guild_id=GUILD_ID)
        auto_dj.start()
        auto_dj.enable(GUILD_ID)

        await auto_dj._on_queue_exhausted(event)

        assert GUILD_ID in auto_dj._timers
        # Clean up
        auto_dj.stop()

    @pytest.mark.asyncio
    async def test_skips_if_guild_not_opted_in(self, auto_dj: AutoDJ) -> None:
        """No timer scheduled when /dj on was never invoked for this guild."""
        event = QueueExhausted(guild_id=GUILD_ID)

        await auto_dj._on_queue_exhausted(event)

        assert GUILD_ID not in auto_dj._timers

    @pytest.mark.asyncio
    async def test_skips_if_radio_already_enabled(
        self, auto_dj: AutoDJ, radio_service: MagicMock
    ) -> None:
        radio_service.is_enabled.return_value = True
        auto_dj.enable(GUILD_ID)
        event = QueueExhausted(guild_id=GUILD_ID)

        await auto_dj._on_queue_exhausted(event)

        assert GUILD_ID not in auto_dj._timers

    @pytest.mark.asyncio
    async def test_skips_if_delay_is_zero(self, auto_dj: AutoDJ) -> None:
        auto_dj.enable(GUILD_ID)
        event = QueueExhausted(guild_id=GUILD_ID)

        with (
            patch("discord_music_player.application.services.auto_dj.TimeConstants") as mock_tc,
            patch(
                "discord_music_player.application.services.auto_dj.asyncio.create_task"
            ) as mock_create_task,
        ):
            mock_tc.AUTO_DJ_DELAY_SECONDS = 0
            await auto_dj._on_queue_exhausted(event)

        assert GUILD_ID not in auto_dj._timers
        mock_create_task.assert_not_called()  # verify the code path actually exited early

    @pytest.mark.asyncio
    async def test_replaces_existing_timer_for_same_guild(self, auto_dj: AutoDJ) -> None:
        event = QueueExhausted(guild_id=GUILD_ID)
        auto_dj.start()
        auto_dj.enable(GUILD_ID)

        await auto_dj._on_queue_exhausted(event)
        first_task = auto_dj._timers[GUILD_ID]

        await auto_dj._on_queue_exhausted(event)
        second_task = auto_dj._timers[GUILD_ID]

        assert first_task is not second_task
        await asyncio.sleep(0)  # let the event loop process the cancellation
        assert first_task.cancelled()  # verify old timer was actually cancelled
        auto_dj.stop()


# ============================================================================
# Track Started → Timer Cancellation
# ============================================================================


class TestOnTrackStarted:
    @pytest.mark.asyncio
    async def test_cancels_pending_timer(self, auto_dj: AutoDJ) -> None:
        auto_dj.start()
        auto_dj.enable(GUILD_ID)

        # Schedule a timer
        event_exhausted = QueueExhausted(guild_id=GUILD_ID)
        await auto_dj._on_queue_exhausted(event_exhausted)
        assert GUILD_ID in auto_dj._timers
        task = auto_dj._timers[GUILD_ID]

        # Track starts → should cancel
        event_started = TrackStartedPlaying(guild_id=GUILD_ID, track_id=TrackId(value="test"))
        await auto_dj._on_track_started(event_started)

        assert GUILD_ID not in auto_dj._timers
        await asyncio.sleep(0)  # let the event loop process the cancellation
        assert task.cancelled()  # verify cancel() was actually called on the task
        auto_dj.stop()

    @pytest.mark.asyncio
    async def test_noop_when_no_timer_exists(self, auto_dj: AutoDJ) -> None:
        event = TrackStartedPlaying(guild_id=GUILD_ID, track_id=TrackId(value="test"))
        await auto_dj._on_track_started(event)  # should not raise


# ============================================================================
# Delayed Activation — Happy Path
# ============================================================================


class TestDelayedActivate:
    @pytest.mark.asyncio
    async def test_activates_radio_and_starts_playback(
        self,
        auto_dj: AutoDJ,
        radio_service: MagicMock,
        playback_service: MagicMock,
        session_repo: MagicMock,
        seed_track: Track,
    ) -> None:
        await auto_dj._delayed_activate(GUILD_ID, delay=0)

        radio_service.toggle_radio.assert_awaited_once_with(
            guild_id=GUILD_ID,
            user_id=seed_track.requested_by_id,
            user_name=seed_track.requested_by_name,
        )
        playback_service.start_playback.assert_awaited_once_with(GUILD_ID)

    @pytest.mark.asyncio
    async def test_injects_and_clears_seed_track(
        self,
        auto_dj: AutoDJ,
        session_repo: MagicMock,
        empty_session: GuildPlaybackSession,
        seed_track: Track,
    ) -> None:
        assert empty_session.current_track is None

        await auto_dj._delayed_activate(GUILD_ID, delay=0)

        # After successful activation, the injected seed should be cleared
        assert empty_session.current_track is None
        # Session saved at least twice (inject seed + clear after toggle)
        assert session_repo.save.await_count >= 2

    @pytest.mark.asyncio
    async def test_uses_default_requester_when_missing(
        self,
        auto_dj: AutoDJ,
        history_repo: MagicMock,
        radio_service: MagicMock,
    ) -> None:
        track_no_requester = Track(
            id=TrackId(value="anon-1"),
            title="Anonymous Track",
            webpage_url="https://youtube.com/watch?v=anon1",
            duration_seconds=120,
        )
        history_repo.get_recent = AsyncMock(return_value=[track_no_requester])

        await auto_dj._delayed_activate(GUILD_ID, delay=0)

        call_kwargs = radio_service.toggle_radio.call_args.kwargs
        # DiscordSnowflake requires gt=0, so 0 is not a valid sentinel —
        # Auto-DJ propagates None when no requester is available.
        assert call_kwargs["user_id"] is None
        assert call_kwargs["user_name"] == "Auto-DJ"


# ============================================================================
# Delayed Activation — Guard Conditions (bail-out paths)
# ============================================================================


class TestDelayedActivateGuards:
    @pytest.mark.asyncio
    async def test_aborts_if_radio_enabled_after_delay(
        self, auto_dj: AutoDJ, radio_service: MagicMock
    ) -> None:
        radio_service.is_enabled.return_value = True

        await auto_dj._delayed_activate(GUILD_ID, delay=0)

        radio_service.toggle_radio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_aborts_if_session_not_found(
        self, auto_dj: AutoDJ, session_repo: MagicMock, radio_service: MagicMock
    ) -> None:
        session_repo.get = AsyncMock(return_value=None)

        await auto_dj._delayed_activate(GUILD_ID, delay=0)

        radio_service.toggle_radio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_aborts_if_session_has_tracks(
        self,
        auto_dj: AutoDJ,
        session_repo: MagicMock,
        radio_service: MagicMock,
        seed_track: Track,
    ) -> None:
        session_with_tracks = GuildPlaybackSession(guild_id=GUILD_ID)
        session_with_tracks.set_current_track(seed_track)
        session_repo.get = AsyncMock(return_value=session_with_tracks)

        await auto_dj._delayed_activate(GUILD_ID, delay=0)

        radio_service.toggle_radio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_aborts_if_session_has_queued_tracks_only(
        self,
        auto_dj: AutoDJ,
        session_repo: MagicMock,
        radio_service: MagicMock,
        seed_track: Track,
    ) -> None:
        """has_tracks is True when queue is non-empty even if current_track is None."""
        session_with_queue = GuildPlaybackSession(guild_id=GUILD_ID)
        session_with_queue.enqueue(seed_track)
        assert session_with_queue.current_track is None
        assert session_with_queue.has_tracks is True
        session_repo.get = AsyncMock(return_value=session_with_queue)

        await auto_dj._delayed_activate(GUILD_ID, delay=0)

        radio_service.toggle_radio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_aborts_if_ai_unavailable(
        self, auto_dj: AutoDJ, ai_client: MagicMock, radio_service: MagicMock
    ) -> None:
        ai_client.is_available = AsyncMock(return_value=False)

        await auto_dj._delayed_activate(GUILD_ID, delay=0)

        radio_service.toggle_radio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_aborts_if_no_history(
        self, auto_dj: AutoDJ, history_repo: MagicMock, radio_service: MagicMock
    ) -> None:
        history_repo.get_recent = AsyncMock(return_value=[])

        await auto_dj._delayed_activate(GUILD_ID, delay=0)

        radio_service.toggle_radio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_on_cancellation(self, auto_dj: AutoDJ, radio_service: MagicMock) -> None:
        """Simulates the asyncio.sleep being cancelled mid-wait."""

        async def _cancelled_sleep(_: int) -> None:
            raise asyncio.CancelledError

        with patch(
            "discord_music_player.application.services.auto_dj.asyncio.sleep", _cancelled_sleep
        ):
            await auto_dj._delayed_activate(GUILD_ID, delay=60)

        radio_service.toggle_radio.assert_not_awaited()


# ============================================================================
# Delayed Activation — Failure Modes
# ============================================================================


class TestDelayedActivateFailures:
    @pytest.mark.asyncio
    async def test_does_not_start_playback_when_toggle_fails(
        self, auto_dj: AutoDJ, radio_service: MagicMock, playback_service: MagicMock
    ) -> None:
        radio_service.toggle_radio = AsyncMock(
            return_value=RadioToggleResult(
                enabled=False,
                tracks_added=0,
                message="No recommendations available.",
            )
        )

        await auto_dj._delayed_activate(GUILD_ID, delay=0)

        playback_service.start_playback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_start_playback_when_zero_tracks_added(
        self, auto_dj: AutoDJ, radio_service: MagicMock, playback_service: MagicMock
    ) -> None:
        radio_service.toggle_radio = AsyncMock(
            return_value=RadioToggleResult(
                enabled=True,
                tracks_added=0,
                message="Radio enabled but no tracks resolved.",
            )
        )

        await auto_dj._delayed_activate(GUILD_ID, delay=0)

        playback_service.start_playback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_toggle_exception_is_caught(
        self, auto_dj: AutoDJ, radio_service: MagicMock, playback_service: MagicMock
    ) -> None:
        radio_service.toggle_radio = AsyncMock(side_effect=RuntimeError("AI exploded"))

        # Should not raise
        await auto_dj._delayed_activate(GUILD_ID, delay=0)

        playback_service.start_playback.assert_not_awaited()


# ============================================================================
# Multi-Guild Isolation
# ============================================================================


class TestMultiGuild:
    @pytest.mark.asyncio
    async def test_separate_timers_per_guild(self, auto_dj: AutoDJ) -> None:
        auto_dj.start()

        guild_a, guild_b = 111, 222
        auto_dj.enable(guild_a)
        auto_dj.enable(guild_b)
        await auto_dj._on_queue_exhausted(QueueExhausted(guild_id=guild_a))
        await auto_dj._on_queue_exhausted(QueueExhausted(guild_id=guild_b))

        assert guild_a in auto_dj._timers
        assert guild_b in auto_dj._timers

        # Cancel only guild_a
        await auto_dj._on_track_started(TrackStartedPlaying(guild_id=guild_a, track_id=TrackId(value="test")))
        assert guild_a not in auto_dj._timers
        assert guild_b in auto_dj._timers

        auto_dj.stop()
