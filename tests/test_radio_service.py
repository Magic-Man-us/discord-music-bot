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
    queue_service.enqueue.return_value = enqueue_result

    session_repo = AsyncMock()
    session_repo.get.return_value = session

    svc = RadioApplicationService(
        ai_client=ai_client,
        audio_resolver=audio_resolver,
        queue_service=queue_service,
        session_repository=session_repo,
        settings=settings or RadioSettings(),
    )

    mocks = {
        "ai_client": ai_client,
        "audio_resolver": audio_resolver,
        "queue_service": queue_service,
        "session_repo": session_repo,
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
