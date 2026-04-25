"""Unit tests for RadioApplicationService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_music_player.application.services.radio_service import (
    RadioApplicationService,
)
from discord_music_player.config.settings import RadioSettings
from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.domain.shared.events import reset_event_bus


def _make_track(title: str = "Test Song", track_id: str = "abc123") -> Track:
    return Track(
        id=TrackId(value=track_id),
        title=title,
        webpage_url=f"https://youtube.com/watch?v={track_id}",
        stream_url="https://stream.example.com/audio.mp3",
    )


def _make_session(current_track: Track | None = None, queue: list[Track] | None = None):
    session = MagicMock()
    session.current_track = current_track
    session.queue = queue or []
    session.queue_length = len(session.queue)
    session.MAX_QUEUE_SIZE = 50
    session.is_idle = True
    return session


def _make_rec(title: str = "Similar Song", artist: str | None = None):
    """Create a mock Recommendation."""
    rec = MagicMock()
    rec.query = title
    rec.title = title
    rec.artist = artist
    rec.dedup_key = f"{(artist or '').lower()}|{title.lower()}"
    return rec


def _make_service(
    *,
    ai_available: bool = True,
    recommendations: list | None = None,
    resolve_returns: Track | None = None,
    enqueue_success: bool = True,
    session: object | None = None,
    settings: RadioSettings | None = None,
) -> tuple[RadioApplicationService, dict[str, AsyncMock]]:
    ai_client = AsyncMock()
    ai_client.is_available.return_value = ai_available
    ai_client.get_recommendations.return_value = recommendations or []

    audio_resolver = AsyncMock()
    audio_resolver.resolve.return_value = resolve_returns

    queue_service = AsyncMock()
    enqueue_result = MagicMock()
    enqueue_result.success = enqueue_success
    enqueue_result.track = resolve_returns if enqueue_success else None
    queue_service.enqueue.return_value = enqueue_result

    session_repo = AsyncMock()
    session_repo.get.return_value = session

    history_repo = AsyncMock()
    history_repo.get_recent.return_value = []

    # Reset event bus to avoid cross-test interference
    reset_event_bus()

    svc = RadioApplicationService(
        ai_client=ai_client,
        audio_resolver=audio_resolver,
        queue_service=queue_service,
        session_repository=session_repo,
        history_repository=history_repo,
        settings=settings or RadioSettings(),
    )

    mocks = {
        "ai_client": ai_client,
        "audio_resolver": audio_resolver,
        "queue_service": queue_service,
        "session_repo": session_repo,
        "history_repo": history_repo,
    }
    return svc, mocks


class TestRadioToggle:
    """Tests for toggle_radio."""

    @pytest.mark.asyncio
    async def test_toggle_on_enables_radio(self):
        """Toggle on should enable radio, enqueue visible_count tracks, and pool the rest."""
        track = _make_track()
        session = _make_session(current_track=track)

        # Create batch_size(10) recommendations
        recs = [_make_rec(title=f"Rec {i}", artist=f"Artist {i}") for i in range(10)]
        resolved = _make_track(title="Resolved", track_id="resolved1")

        svc, mocks = _make_service(
            ai_available=True,
            recommendations=recs,
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
        )

        result = await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")

        assert result.enabled is True
        # Default visible_count=3, so 3 tracks enqueued
        assert result.tracks_added == 3
        assert len(result.generated_tracks) == 3
        assert result.seed_title == track.title
        assert svc.is_enabled(1)

        # Remaining 7 should be in the pool
        state = svc.get_state(1)
        assert state is not None
        assert len(state.pool) == 7

    @pytest.mark.asyncio
    async def test_toggle_off_disables_radio(self):
        """Toggle when already enabled should disable radio."""
        track = _make_track()
        session = _make_session(current_track=track)

        recs = [_make_rec(title=f"Rec {i}") for i in range(3)]
        resolved = _make_track(title="Similar Song", track_id="resolved1")

        svc, _ = _make_service(
            ai_available=True,
            recommendations=recs,
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
        )

        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert svc.is_enabled(1)

        result = await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert result.enabled is False
        assert not svc.is_enabled(1)

    @pytest.mark.asyncio
    async def test_toggle_no_current_track(self):
        """Toggle with no current track should fail."""
        session = _make_session(current_track=None)
        svc, _ = _make_service(session=session)

        result = await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert result.enabled is False

    @pytest.mark.asyncio
    async def test_toggle_ai_unavailable(self):
        """Toggle when AI is unavailable should fail."""
        track = _make_track()
        session = _make_session(current_track=track)
        svc, _ = _make_service(ai_available=False, session=session)

        result = await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert result.enabled is False

    @pytest.mark.asyncio
    async def test_toggle_no_recommendations(self):
        """Toggle when AI returns no recommendations should fail."""
        track = _make_track()
        session = _make_session(current_track=track)
        svc, _ = _make_service(ai_available=True, recommendations=[], session=session)

        result = await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert result.enabled is False

    @pytest.mark.asyncio
    async def test_toggle_stores_channel_id(self):
        """Toggle should store channel_id on state for pool-exhaustion events."""
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"Rec {i}") for i in range(3)]
        resolved = _make_track(title="Resolved", track_id="res1")

        svc, _ = _make_service(
            ai_available=True,
            recommendations=recs,
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
        )

        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User", channel_id=555)
        state = svc.get_state(1)
        assert state is not None
        assert state.channel_id == 555
        assert state.user_id == 100


class TestRadioDisable:
    """Tests for disable_radio."""

    @pytest.mark.asyncio
    async def test_disable_clears_state(self):
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"Rec {i}") for i in range(3)]
        resolved = _make_track(title="Similar", track_id="res1")

        svc, _ = _make_service(
            ai_available=True,
            recommendations=recs,
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
        )

        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert svc.is_enabled(1)

        svc.disable_radio(1)
        assert not svc.is_enabled(1)

    def test_disable_noop_when_not_enabled(self):
        svc, _ = _make_service()
        svc.disable_radio(999)


class TestReplenishFromPool:
    """Tests for replenish_from_pool."""

    @pytest.mark.asyncio
    async def test_replenish_pops_from_pool(self):
        """replenish_from_pool should resolve and enqueue one track from the pool."""
        track = _make_track()
        session = _make_session(current_track=track)

        recs = [_make_rec(title=f"Rec {i}", artist=f"Artist {i}") for i in range(5)]
        resolved = _make_track(title="Resolved", track_id="res1")

        svc, mocks = _make_service(
            ai_available=True,
            recommendations=recs,
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
            settings=RadioSettings(batch_size=5, visible_count=2),
        )

        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")

        state = svc.get_state(1)
        assert state is not None
        initial_pool_size = len(state.pool)
        assert initial_pool_size == 3  # 5 - 2 visible

        added = await svc.replenish_from_pool(1)
        assert added == 1
        assert len(state.pool) == initial_pool_size - 1

    @pytest.mark.asyncio
    async def test_replenish_publishes_event_when_pool_empty(self):
        """replenish_from_pool should publish RadioPoolExhausted when pool is empty."""
        from discord_music_player.domain.shared.events import RadioPoolExhausted, get_event_bus

        track = _make_track()
        session = _make_session(current_track=track)

        # Only visible_count recs — pool will be empty after toggle
        recs = [_make_rec(title=f"Rec {i}") for i in range(3)]
        resolved = _make_track(title="Resolved", track_id="res1")

        svc, _ = _make_service(
            ai_available=True,
            recommendations=recs,
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
            settings=RadioSettings(batch_size=3, visible_count=3),
        )

        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User", channel_id=555)

        state = svc.get_state(1)
        assert state is not None
        assert len(state.pool) == 0

        handler = AsyncMock()
        get_event_bus().subscribe(RadioPoolExhausted, handler)

        await svc.replenish_from_pool(1)

        handler.assert_awaited_once()
        event = handler.call_args[0][0]
        assert event.guild_id == 1
        assert event.channel_id == 555


class TestContinueRadio:
    """Tests for continue_radio."""

    @pytest.mark.asyncio
    async def test_continue_fetches_new_batch(self):
        """continue_radio should fetch a new batch and refill the pool."""
        track = _make_track()
        session = _make_session(current_track=track)

        initial_recs = [_make_rec(title=f"Init {i}") for i in range(3)]
        resolved = _make_track(title="Resolved", track_id="res1")

        svc, mocks = _make_service(
            ai_available=True,
            recommendations=initial_recs,
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
        )

        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert svc.is_enabled(1)

        # Set up new batch for continue
        new_recs = [_make_rec(title=f"New {i}", artist=f"Artist {i}") for i in range(8)]
        mocks["ai_client"].get_recommendations.return_value = new_recs

        result = await svc.continue_radio(1)

        assert result.enabled is True
        assert result.tracks_added == 3  # visible_count
        state = svc.get_state(1)
        assert state is not None
        assert len(state.pool) == 5  # 8 - 3

    @pytest.mark.asyncio
    async def test_continue_when_not_active(self):
        svc, _ = _make_service()
        result = await svc.continue_radio(1)
        assert result.enabled is False


class TestRadioRefill:
    """Tests for refill_queue (now pool-aware)."""

    @pytest.mark.asyncio
    async def test_refill_when_not_enabled(self):
        svc, _ = _make_service()
        result = await svc.refill_queue(guild_id=1)
        assert result == 0

    @pytest.mark.asyncio
    async def test_refill_respects_session_limit(self):
        """Refill should disable radio when session limit is reached."""
        track = _make_track()
        session = _make_session(current_track=track)

        recs = [_make_rec(title=f"Rec {i}") for i in range(3)]
        resolved = _make_track(title="Resolved", track_id="res1")

        settings = RadioSettings(batch_size=3, visible_count=3, max_tracks_per_session=5)

        svc, _ = _make_service(
            ai_available=True,
            recommendations=recs,
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
            settings=settings,
        )

        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert svc.is_enabled(1)

        # Manually set tracks_consumed to the limit
        svc._states[1].tracks_consumed = 5

        result = await svc.refill_queue(guild_id=1)
        assert result == 0
        assert not svc.is_enabled(1)

    @pytest.mark.asyncio
    async def test_refill_draws_from_pool(self):
        """Refill should draw from pool rather than calling AI directly."""
        track = _make_track()
        session = _make_session(current_track=track)

        recs = [_make_rec(title=f"Rec {i}", artist=f"Artist {i}") for i in range(6)]
        resolved = _make_track(title="Resolved", track_id="res1")

        svc, mocks = _make_service(
            ai_available=True,
            recommendations=recs,
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
            settings=RadioSettings(batch_size=6, visible_count=3),
        )

        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert svc.is_enabled(1)

        state = svc.get_state(1)
        assert state is not None
        assert len(state.pool) == 3  # 6 - 3

        # Reset AI mock call count — refill should NOT call AI
        mocks["ai_client"].get_recommendations.reset_mock()

        added = await svc.refill_queue(guild_id=1)
        assert added > 0
        mocks["ai_client"].get_recommendations.assert_not_awaited()


class TestRadioReroll:
    """Tests for reroll_track."""

    @pytest.mark.asyncio
    async def test_reroll_replaces_track(self):
        track = _make_track()
        queued = _make_track(title="Old Rec", track_id="old1")
        session = _make_session(current_track=track, queue=[queued])

        rec = _make_rec(title="New Rec")
        new_track = _make_track(title="New Rec", track_id="new1")

        svc, mocks = _make_service(
            ai_available=True,
            recommendations=[_make_rec(title=f"Init {i}") for i in range(3)],
            resolve_returns=queued,
            enqueue_success=True,
            session=session,
        )

        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert svc.is_enabled(1)

        # Set up for the reroll
        mocks["ai_client"].get_recommendations.return_value = [rec]
        mocks["audio_resolver"].resolve.return_value = new_track

        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.track = new_track
        mocks["queue_service"].enqueue.return_value = enqueue_result
        mocks["queue_service"].remove.return_value = queued

        empty_session = _make_session(current_track=track, queue=[])
        mocks["session_repo"].get.return_value = empty_session

        result = await svc.reroll_track(guild_id=1, queue_position=0, user_id=100, user_name="User")

        assert result is not None
        assert result.title == "New Rec"
        mocks["queue_service"].remove.assert_awaited_once_with(1, 0)

    @pytest.mark.asyncio
    async def test_reroll_when_not_enabled(self):
        svc, _ = _make_service()
        result = await svc.reroll_track(guild_id=1, queue_position=0, user_id=100, user_name="User")
        assert result is None


class TestRadioAutoRefill:
    """Tests for RadioAutoRefill subscriber."""

    @pytest.mark.asyncio
    async def test_subscriber_start_stop(self):
        from discord_music_player.application.services.radio_auto_refill import RadioAutoRefill

        reset_event_bus()

        radio_service = AsyncMock()
        playback_service = AsyncMock()

        subscriber = RadioAutoRefill(
            radio_service=radio_service,
            playback_service=playback_service,
        )

        subscriber.start()
        assert subscriber._started is True

        subscriber.stop()
        assert subscriber._started is False

        reset_event_bus()

    @pytest.mark.asyncio
    async def test_subscriber_triggers_refill(self):
        from discord_music_player.application.services.radio_auto_refill import RadioAutoRefill
        from discord_music_player.domain.shared.events import (
            QueueExhausted,
            get_event_bus,
        )

        reset_event_bus()

        radio_service = MagicMock()
        radio_service.is_enabled.return_value = True
        radio_service.refill_queue = AsyncMock(return_value=3)

        playback_service = AsyncMock()

        subscriber = RadioAutoRefill(
            radio_service=radio_service,
            playback_service=playback_service,
        )
        subscriber.start()

        event = QueueExhausted(
            guild_id=1,
            last_track_id=TrackId(value="abc"),
            last_track_title="Test Song",
        )
        await get_event_bus().publish(event)

        radio_service.refill_queue.assert_awaited_once_with(1)
        playback_service.start_playback.assert_awaited_once_with(1)

        subscriber.stop()
        reset_event_bus()

    @pytest.mark.asyncio
    async def test_subscriber_skips_when_disabled(self):
        from discord_music_player.application.services.radio_auto_refill import RadioAutoRefill
        from discord_music_player.domain.shared.events import (
            QueueExhausted,
            get_event_bus,
        )

        reset_event_bus()

        radio_service = MagicMock()
        radio_service.is_enabled.return_value = False
        radio_service.refill_queue = AsyncMock()

        playback_service = AsyncMock()

        subscriber = RadioAutoRefill(
            radio_service=radio_service,
            playback_service=playback_service,
        )
        subscriber.start()

        event = QueueExhausted(
            guild_id=1, last_track_id=TrackId(value="abc"), last_track_title="Test"
        )
        await get_event_bus().publish(event)

        radio_service.refill_queue.assert_not_awaited()
        playback_service.start_playback.assert_not_awaited()

        subscriber.stop()
        reset_event_bus()


# =============================================================================
# warmup_next + _publish_pool_exhausted
# =============================================================================


class TestWarmupNext:
    @pytest.mark.asyncio
    async def test_returns_zero_when_radio_inactive(self):
        svc, _ = _make_service()
        assert await svc.warmup_next(guild_id=1) == 0

    @pytest.mark.asyncio
    async def test_returns_zero_at_session_limit(self):
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, _ = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            session=session,
            settings=RadioSettings(batch_size=3, visible_count=3, max_tracks_per_session=1),
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        # Simulate session limit reached
        state = svc.get_state(1)
        state.tracks_consumed = state.tracks_consumed.__class__(99) if hasattr(state.tracks_consumed, "__class__") else 99
        # Simpler: just bump counter directly
        state.tracks_consumed = 999

        assert await svc.warmup_next(1) == 0

    @pytest.mark.asyncio
    async def test_returns_zero_when_session_missing(self):
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            session=session,
            settings=RadioSettings(batch_size=3, visible_count=3),
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        # Now make session_repo return None
        mocks["session_repo"].get.return_value = None
        assert await svc.warmup_next(1) == 0

    @pytest.mark.asyncio
    async def test_returns_zero_when_queue_not_empty(self):
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            session=session,
            settings=RadioSettings(batch_size=3, visible_count=3),
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        # Make next session check show non-empty queue
        non_empty = _make_session(current_track=track, queue=[track])
        mocks["session_repo"].get.return_value = non_empty
        assert await svc.warmup_next(1) == 0

    @pytest.mark.asyncio
    async def test_publishes_exhausted_when_pool_empty(self):
        from discord_music_player.domain.shared.events import RadioPoolExhausted, get_event_bus

        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            session=session,
            settings=RadioSettings(batch_size=3, visible_count=3),
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U", channel_id=42)

        # Empty queue session
        empty_session = _make_session(current_track=track, queue=[])
        mocks["session_repo"].get.return_value = empty_session

        # Drain pool to empty
        state = svc.get_state(1)
        state.pool = []

        handler = AsyncMock()
        get_event_bus().subscribe(RadioPoolExhausted, handler)

        result = await svc.warmup_next(1)

        assert result == 0
        handler.assert_awaited_once()
        assert handler.call_args[0][0].channel_id == 42

    @pytest.mark.asyncio
    async def test_happy_path_drains_one_track(self):
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"r{i}") for i in range(5)]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            session=session,
            settings=RadioSettings(batch_size=5, visible_count=2),
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        empty_session = _make_session(current_track=track, queue=[])
        mocks["session_repo"].get.return_value = empty_session

        # Pool has 3 items after toggle; drain should pull one
        result = await svc.warmup_next(1)
        assert result == 1


class TestPublishPoolExhausted:
    @pytest.mark.asyncio
    async def test_publishes_event_with_state_data(self):
        from discord_music_player.application.services.radio_service import RadioState
        from discord_music_player.domain.shared.events import RadioPoolExhausted, get_event_bus

        svc, _ = _make_service()
        state = RadioState(
            enabled=True,
            user_id=100,
            user_name="U",
            seed_track_title="seed",
            channel_id=999,
        )
        state.tracks_consumed = 7

        handler = AsyncMock()
        get_event_bus().subscribe(RadioPoolExhausted, handler)

        await svc._publish_pool_exhausted(guild_id=1, state=state)

        handler.assert_awaited_once()
        event = handler.call_args[0][0]
        assert event.guild_id == 1
        assert event.channel_id == 999
        assert event.tracks_generated == 7


# =============================================================================
# continue_radio — missing branches
# =============================================================================


class TestContinueRadioBranches:
    @pytest.mark.asyncio
    async def test_returns_no_track_message_when_base_track_missing(self):
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            session=session,
            settings=RadioSettings(batch_size=3, visible_count=3),
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        # Make base_track lookup fail
        mocks["session_repo"].get.return_value = None

        result = await svc.continue_radio(1)

        assert result.enabled is False
        assert "currently playing" in result.message.lower()

    @pytest.mark.asyncio
    async def test_disables_when_session_budget_exhausted(self):
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, _ = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            session=session,
            settings=RadioSettings(batch_size=3, visible_count=3, max_tracks_per_session=2),
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        state = svc.get_state(1)
        state.tracks_consumed = 100  # exhausted

        result = await svc.continue_radio(1)

        assert result.enabled is False
        assert "limit" in result.message.lower()
        assert svc.is_enabled(1) is False

    @pytest.mark.asyncio
    async def test_returns_enabled_message_when_no_recommendations(self):
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            session=session,
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        # Continue but AI returns nothing
        mocks["ai_client"].get_recommendations.return_value = []

        result = await svc.continue_radio(1)

        assert result.enabled is True
        assert "couldn't find" in result.message.lower()


# =============================================================================
# reroll_track — missing branches + _restore_removed_track
# =============================================================================


class TestRerollBranches:
    @pytest.mark.asyncio
    async def test_returns_none_when_base_track_missing(self):
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            session=session,
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        mocks["session_repo"].get.return_value = None

        result = await svc.reroll_track(guild_id=1, queue_position=0, user_id=100, user_name="U")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_remove_returns_none(self):
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            session=session,
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        mocks["queue_service"].remove.return_value = None

        result = await svc.reroll_track(guild_id=1, queue_position=0, user_id=100, user_name="U")
        assert result is None

    @pytest.mark.asyncio
    async def test_restores_track_when_no_recommendations(self):
        track = _make_track()
        session = _make_session(current_track=track)
        initial_recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=initial_recs,
            resolve_returns=resolved,
            session=session,
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        # Remove returns the existing queued track
        removed = _make_track(title="Removed", track_id="rem1")
        mocks["queue_service"].remove.return_value = removed

        # AI returns no recs after removal
        mocks["ai_client"].get_recommendations.return_value = []

        result = await svc.reroll_track(guild_id=1, queue_position=2, user_id=100, user_name="U")

        assert result is None
        # _restore_removed_track called enqueue
        assert mocks["queue_service"].enqueue.called

    @pytest.mark.asyncio
    async def test_restores_track_when_resolve_first_fails(self):
        track = _make_track()
        session = _make_session(current_track=track)
        initial_recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=initial_recs,
            resolve_returns=resolved,
            session=session,
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        removed = _make_track(title="Removed", track_id="rem1")
        mocks["queue_service"].remove.return_value = removed
        # New batch fetched, but resolver returns None for all
        mocks["ai_client"].get_recommendations.return_value = [_make_rec(title="x")]
        mocks["audio_resolver"].resolve.return_value = None

        result = await svc.reroll_track(guild_id=1, queue_position=2, user_id=100, user_name="U")
        assert result is None


class TestRestoreRemovedTrack:
    @pytest.mark.asyncio
    async def test_happy_path_calls_move_when_position_differs(self):
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            session=session,
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        # Set up: enqueue succeeds; new session has queue_length=3
        new_session = _make_session(current_track=track, queue=[track, track, track])
        mocks["session_repo"].get.return_value = new_session

        await svc._restore_removed_track(
            guild_id=1, track=track, position=0, user_id=100, user_name="U"
        )

        # from_pos=2 (queue_length-1), position=0, so move was called
        mocks["queue_service"].move.assert_called_with(1, 2, 0)

    @pytest.mark.asyncio
    async def test_swallows_exception(self):
        track = _make_track()
        session = _make_session(current_track=track)
        recs = [_make_rec(title=f"r{i}") for i in range(3)]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            session=session,
        )
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="U")

        # Force enqueue to raise — _restore_removed_track must swallow it.
        mocks["queue_service"].enqueue.side_effect = RuntimeError("boom")

        # Should not raise.
        await svc._restore_removed_track(
            guild_id=1, track=track, position=0, user_id=100, user_name="U"
        )


# =============================================================================
# _try_resolve_and_enqueue error paths
# =============================================================================


class TestTryResolveErrorPaths:
    @pytest.mark.asyncio
    async def test_returns_none_when_resolver_returns_none(self):
        recs = [_make_rec(title="r0")]
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=None,  # resolver returns None
            session=_make_session(current_track=_make_track()),
        )
        rec = recs[0]
        result = await svc._try_resolve_and_enqueue(
            rec, guild_id=1, user_id=100, user_name="U"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_resolver_raises(self):
        recs = [_make_rec(title="r0")]
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=_make_track(track_id="x"),
            session=_make_session(current_track=_make_track()),
        )
        mocks["audio_resolver"].resolve.side_effect = RuntimeError("net down")

        # The exception path returns None instead of bubbling.
        result = await svc._try_resolve_and_enqueue(
            recs[0], guild_id=1, user_id=100, user_name="U"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_enqueue_unsuccessful(self):
        recs = [_make_rec(title="r0")]
        resolved = _make_track(track_id="x")
        svc, mocks = _make_service(
            recommendations=recs,
            resolve_returns=resolved,
            enqueue_success=False,  # enqueue.success=False
            session=_make_session(current_track=_make_track()),
        )
        result = await svc._try_resolve_and_enqueue(
            recs[0], guild_id=1, user_id=100, user_name="U"
        )
        assert result is None
