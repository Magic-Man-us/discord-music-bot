"""
Additional Events Tests for Coverage

Tests edge cases and uncovered code paths in events module.
"""

from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.shared.events import (
    BotJoinedVoiceChannel,
    DomainEvent,
    EventBus,
    TrackFinishedPlaying,
    TrackStartedPlaying,
    get_event_bus,
    reset_event_bus,
)


class TestDomainEventEdgeCases:
    """Tests for DomainEvent edge cases."""

    def test_domain_event_has_event_id(self):
        """Should generate unique event IDs."""
        event1 = DomainEvent()
        event2 = DomainEvent()

        assert event1.event_id != event2.event_id

    def test_domain_event_has_occurred_at(self):
        """Should set occurred_at timestamp."""
        event = DomainEvent()

        assert event.occurred_at is not None

    def test_domain_event_post_init(self):
        """Should call __post_init__ without errors."""
        # __post_init__ currently just passes, but we test it's called
        event = DomainEvent()
        assert event is not None


class TestEventBusEdgeCases:
    """Tests for EventBus edge cases and uncovered paths."""

    async def test_publish_with_no_handlers(self):
        """Should handle publishing event with no subscribers."""
        bus = EventBus()
        event = TrackStartedPlaying(
            guild_id=123, track_id=TrackId("test"), track_title="Test Song", track_url="https://test.com"
        )

        # Should not raise - just logs and returns
        await bus.publish(event)

    async def test_unsubscribe_handler(self):
        """Should remove handler from event type."""
        bus = EventBus()
        handler_called = []

        async def handler(event: TrackStartedPlaying):
            handler_called.append(event)

        # Subscribe then unsubscribe
        bus.subscribe(TrackStartedPlaying, handler)
        bus.unsubscribe(TrackStartedPlaying, handler)

        # Publish event
        event = TrackStartedPlaying(
            guild_id=123, track_id=TrackId("test"), track_title="Test Song", track_url="https://test.com"
        )
        await bus.publish(event)

        # Handler should not have been called
        assert len(handler_called) == 0

    async def test_unsubscribe_nonexistent_handler(self):
        """Should handle unsubscribing a handler that was never subscribed."""
        bus = EventBus()

        async def handler(event: TrackStartedPlaying):
            pass

        # Should not raise - just does nothing
        bus.unsubscribe(TrackStartedPlaying, handler)

    async def test_publish_with_handler_exception(self):
        """Should handle exceptions in event handlers gracefully."""
        bus = EventBus()
        handler1_called = []
        handler2_called = []

        async def failing_handler(event: TrackStartedPlaying):
            handler1_called.append(event)
            raise RuntimeError("Handler error")

        async def working_handler(event: TrackStartedPlaying):
            handler2_called.append(event)

        bus.subscribe(TrackStartedPlaying, failing_handler)
        bus.subscribe(TrackStartedPlaying, working_handler)

        event = TrackStartedPlaying(
            guild_id=123, track_id=TrackId("test"), track_title="Test Song", track_url="https://test.com"
        )

        # Should not raise - errors are logged
        await bus.publish(event)

        # Both handlers should have been called despite first one failing
        assert len(handler1_called) == 1
        assert len(handler2_called) == 1

    async def test_clear_removes_all_handlers(self):
        """Should remove all event handlers."""
        bus = EventBus()
        handler_called = []

        async def handler(event: TrackStartedPlaying):
            handler_called.append(event)

        bus.subscribe(TrackStartedPlaying, handler)
        bus.clear()

        # Publish event after clearing
        event = TrackStartedPlaying(
            guild_id=123, track_id=TrackId("test"), track_title="Test Song", track_url="https://test.com"
        )
        await bus.publish(event)

        # Handler should not be called
        assert len(handler_called) == 0

    async def test_multiple_handlers_for_same_event(self):
        """Should call all handlers for an event type."""
        bus = EventBus()
        handler1_called = []
        handler2_called = []

        async def handler1(event: TrackStartedPlaying):
            handler1_called.append(event)

        async def handler2(event: TrackStartedPlaying):
            handler2_called.append(event)

        bus.subscribe(TrackStartedPlaying, handler1)
        bus.subscribe(TrackStartedPlaying, handler2)

        event = TrackStartedPlaying(
            guild_id=123, track_id=TrackId("test"), track_title="Test Song", track_url="https://test.com"
        )
        await bus.publish(event)

        assert len(handler1_called) == 1
        assert len(handler2_called) == 1

    async def test_handlers_for_different_events(self):
        """Should only call handlers for matching event type."""
        bus = EventBus()
        track_started_called = []
        track_finished_called = []

        async def on_started(event: TrackStartedPlaying):
            track_started_called.append(event)

        async def on_finished(event: TrackFinishedPlaying):
            track_finished_called.append(event)

        bus.subscribe(TrackStartedPlaying, on_started)
        bus.subscribe(TrackFinishedPlaying, on_finished)

        # Publish TrackStartedPlaying
        started_event = TrackStartedPlaying(
            guild_id=123, track_id=TrackId("test"), track_title="Test Song", track_url="https://test.com"
        )
        await bus.publish(started_event)

        assert len(track_started_called) == 1
        assert len(track_finished_called) == 0


class TestGlobalEventBus:
    """Tests for global event bus functions."""

    def test_get_event_bus_creates_instance(self):
        """Should create global event bus instance."""
        reset_event_bus()  # Ensure clean slate

        bus = get_event_bus()

        assert bus is not None
        assert isinstance(bus, EventBus)

    def test_get_event_bus_returns_same_instance(self):
        """Should return the same instance on multiple calls."""
        reset_event_bus()

        bus1 = get_event_bus()
        bus2 = get_event_bus()

        assert bus1 is bus2

    def test_reset_event_bus_clears_handlers(self):
        """Should clear handlers and reset instance."""
        bus = get_event_bus()

        async def handler(event: BotJoinedVoiceChannel):
            pass

        bus.subscribe(BotJoinedVoiceChannel, handler)

        # Reset
        reset_event_bus()

        # Get new instance
        new_bus = get_event_bus()

        # Should have no handlers
        assert len(new_bus._handlers) == 0

    def test_reset_event_bus_when_none(self):
        """Should handle resetting when bus is None."""
        reset_event_bus()
        reset_event_bus()  # Second reset should not raise

        bus = get_event_bus()
        assert bus is not None
