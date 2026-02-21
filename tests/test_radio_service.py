"""Unit tests for RadioApplicationService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_music_player.application.services.radio_service import (
    RadioApplicationService,
)
from discord_music_player.config.settings import RadioSettings
from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.value_objects import TrackId


def _make_track(title: str = "Test Song", track_id: str = "abc123") -> Track:
    return Track(
        id=TrackId(track_id),
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
    return session


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
        """Toggle on with a current track should enable radio and enqueue tracks."""
        track = _make_track()
        session = _make_session(current_track=track)

        rec = MagicMock()
        rec.query = "Similar Song"
        rec.title = "Similar Song"
        rec.artist = None

        resolved = _make_track(title="Similar Song", track_id="resolved1")

        svc, mocks = _make_service(
            ai_available=True,
            recommendations=[rec],
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
        )

        result = await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")

        assert result.enabled is True
        assert result.tracks_added == 1
        assert len(result.generated_tracks) == 1
        assert result.generated_tracks[0].title == "Similar Song"
        assert result.seed_title == track.title
        assert svc.is_enabled(1)

    @pytest.mark.asyncio
    async def test_toggle_off_disables_radio(self):
        """Toggle when already enabled should disable radio."""
        track = _make_track()
        session = _make_session(current_track=track)

        rec = MagicMock()
        rec.query = "Similar Song"
        rec.title = "Similar Song"
        rec.artist = None

        resolved = _make_track(title="Similar Song", track_id="resolved1")

        svc, _ = _make_service(
            ai_available=True,
            recommendations=[rec],
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
        )

        # Enable first
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert svc.is_enabled(1)

        # Toggle again to disable
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
        assert not svc.is_enabled(1)

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

        svc, _ = _make_service(
            ai_available=True,
            recommendations=[],
            session=session,
        )

        result = await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")

        assert result.enabled is False


class TestRadioDisable:
    """Tests for disable_radio."""

    @pytest.mark.asyncio
    async def test_disable_clears_state(self):
        """disable_radio should clear the guild's radio state."""
        track = _make_track()
        session = _make_session(current_track=track)

        rec = MagicMock()
        rec.query = "Similar Song"
        rec.title = "Similar Song"
        rec.artist = None

        resolved = _make_track(title="Similar Song", track_id="resolved1")

        svc, _ = _make_service(
            ai_available=True,
            recommendations=[rec],
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
        )

        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert svc.is_enabled(1)

        svc.disable_radio(1)
        assert not svc.is_enabled(1)

    def test_disable_noop_when_not_enabled(self):
        """disable_radio on a guild that isn't enabled should be a no-op."""
        svc, _ = _make_service()
        svc.disable_radio(999)  # Should not raise


class TestRadioRefill:
    """Tests for refill_queue."""

    @pytest.mark.asyncio
    async def test_refill_when_not_enabled(self):
        """Refill should return 0 when radio is not enabled."""
        svc, _ = _make_service()
        result = await svc.refill_queue(guild_id=1)
        assert result == 0

    @pytest.mark.asyncio
    async def test_refill_respects_session_limit(self):
        """Refill should disable radio when session limit is reached."""
        track = _make_track()
        session = _make_session(current_track=track)

        rec = MagicMock()
        rec.query = "Similar Song"
        rec.title = "Similar Song"
        rec.artist = None

        resolved = _make_track(title="Similar Song", track_id="resolved1")

        settings = RadioSettings(default_count=5, max_tracks_per_session=5)

        svc, _ = _make_service(
            ai_available=True,
            recommendations=[rec],
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
            settings=settings,
        )

        # Enable radio (adds 1 track, so tracks_generated = 1)
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert svc.is_enabled(1)

        # Manually set tracks_generated to the limit
        svc._states[1].tracks_generated = 5

        result = await svc.refill_queue(guild_id=1)
        assert result == 0
        assert not svc.is_enabled(1)

    @pytest.mark.asyncio
    async def test_refill_adds_tracks(self):
        """Refill should add tracks when radio is enabled and under limit."""
        track = _make_track()
        session = _make_session(current_track=track)

        rec = MagicMock()
        rec.query = "Another Song"
        rec.title = "Another Song"
        rec.artist = None

        resolved = _make_track(title="Another Song", track_id="another1")

        svc, mocks = _make_service(
            ai_available=True,
            recommendations=[rec],
            resolve_returns=resolved,
            enqueue_success=True,
            session=session,
        )

        # Enable radio
        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert svc.is_enabled(1)

        # Refill
        added = await svc.refill_queue(guild_id=1)
        assert added == 1


class TestRadioReroll:
    """Tests for reroll_track."""

    @pytest.mark.asyncio
    async def test_reroll_replaces_track(self):
        """reroll_track should remove the old track and enqueue a new one."""
        track = _make_track()
        queued = _make_track(title="Old Rec", track_id="old1")
        session = _make_session(current_track=track, queue=[queued])

        rec = MagicMock()
        rec.query = "New Rec"
        rec.title = "New Rec"
        rec.artist = None

        new_track = _make_track(title="New Rec", track_id="new1")

        svc, mocks = _make_service(
            ai_available=True,
            recommendations=[rec],
            resolve_returns=new_track,
            enqueue_success=True,
            session=session,
        )

        # Enable radio first
        enable_rec = MagicMock()
        enable_rec.query = "Old Rec"
        enable_rec.title = "Old Rec"
        enable_rec.artist = None
        mocks["ai_client"].get_recommendations.return_value = [enable_rec]
        mocks["audio_resolver"].resolve.return_value = queued

        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert svc.is_enabled(1)

        # Now set up for the reroll
        mocks["ai_client"].get_recommendations.return_value = [rec]
        mocks["audio_resolver"].resolve.return_value = new_track
        mocks["queue_service"].remove.return_value = queued

        # After removal, session has empty queue
        empty_session = _make_session(current_track=track, queue=[])
        mocks["session_repo"].get.return_value = empty_session

        result = await svc.reroll_track(
            guild_id=1, queue_position=0, user_id=100, user_name="User"
        )

        assert result is not None
        assert result.title == "New Rec"
        mocks["queue_service"].remove.assert_awaited_once_with(1, 0)

    @pytest.mark.asyncio
    async def test_reroll_moves_track_to_original_position(self):
        """reroll_track should move the new track back to the original queue position."""
        track = _make_track()
        q1 = _make_track(title="Q1", track_id="q1")
        q2 = _make_track(title="Q2", track_id="q2")
        q3 = _make_track(title="Q3", track_id="q3")
        session = _make_session(current_track=track, queue=[q1, q2, q3])

        rec = MagicMock()
        rec.query = "Replacement"
        rec.title = "Replacement"
        rec.artist = None

        new_track = _make_track(title="Replacement", track_id="rep1")

        svc, mocks = _make_service(
            ai_available=True,
            recommendations=[rec],
            resolve_returns=new_track,
            enqueue_success=True,
            session=session,
        )

        # Enable radio
        enable_rec = MagicMock()
        enable_rec.query = "Q1"
        enable_rec.title = "Q1"
        enable_rec.artist = None
        mocks["ai_client"].get_recommendations.return_value = [enable_rec]
        mocks["audio_resolver"].resolve.return_value = q1

        await svc.toggle_radio(guild_id=1, user_id=100, user_name="User")
        assert svc.is_enabled(1)

        # Set up for reroll at position 1 (middle track)
        mocks["ai_client"].get_recommendations.return_value = [rec]
        mocks["audio_resolver"].resolve.return_value = new_track
        mocks["queue_service"].remove.return_value = q2

        # reroll_track calls session_repo.get 3 times:
        # 1. Initial fetch (to get base_track)
        # 2. Re-fetch after removal (to build exclusion set)
        # 3. Re-fetch after enqueue (to compute from_pos for move)
        initial = _make_session(current_track=track, queue=[q1, q2, q3])
        after_remove = _make_session(current_track=track, queue=[q1, q3])
        after_enqueue = _make_session(current_track=track, queue=[q1, q3, new_track])
        mocks["session_repo"].get.side_effect = [initial, after_remove, after_enqueue]

        result = await svc.reroll_track(
            guild_id=1, queue_position=1, user_id=100, user_name="User"
        )

        assert result is not None
        assert result.title == "Replacement"
        mocks["queue_service"].remove.assert_awaited_once_with(1, 1)
        # New track was at position 2 (end), should be moved to position 1
        mocks["queue_service"].move.assert_awaited_once_with(1, 2, 1)

    @pytest.mark.asyncio
    async def test_reroll_when_not_enabled(self):
        """reroll_track should return None when radio is not enabled."""
        svc, _ = _make_service()
        result = await svc.reroll_track(
            guild_id=1, queue_position=0, user_id=100, user_name="User"
        )
        assert result is None


class TestRadioAutoRefill:
    """Tests for RadioAutoRefill subscriber."""

    @pytest.mark.asyncio
    async def test_subscriber_start_stop(self):
        """Subscriber should subscribe/unsubscribe without error."""
        from discord_music_player.application.services.radio_auto_refill import (
            RadioAutoRefill,
        )
        from discord_music_player.domain.shared.events import reset_event_bus

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
        """Subscriber should call refill and start playback on QueueExhausted."""
        from discord_music_player.application.services.radio_auto_refill import (
            RadioAutoRefill,
        )
        from discord_music_player.domain.shared.events import (
            QueueExhausted,
            get_event_bus,
            reset_event_bus,
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
            last_track_id=TrackId("abc"),
            last_track_title="Test Song",
        )
        await get_event_bus().publish(event)

        radio_service.refill_queue.assert_awaited_once_with(1)
        playback_service.start_playback.assert_awaited_once_with(1)

        subscriber.stop()
        reset_event_bus()

    @pytest.mark.asyncio
    async def test_subscriber_skips_when_disabled(self):
        """Subscriber should not refill when radio is disabled."""
        from discord_music_player.application.services.radio_auto_refill import (
            RadioAutoRefill,
        )
        from discord_music_player.domain.shared.events import (
            QueueExhausted,
            get_event_bus,
            reset_event_bus,
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

        event = QueueExhausted(guild_id=1, last_track_id=TrackId("abc"), last_track_title="Test")
        await get_event_bus().publish(event)

        radio_service.refill_queue.assert_not_awaited()
        playback_service.start_playback.assert_not_awaited()

        subscriber.stop()
        reset_event_bus()
