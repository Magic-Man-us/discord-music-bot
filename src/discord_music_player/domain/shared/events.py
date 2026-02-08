"""Domain Events Infrastructure.

This module provides the event bus for publishing and subscribing to domain events.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar
from uuid import uuid4

from discord_music_player.domain.shared.datetime_utils import utcnow

logger = logging.getLogger(__name__)

# Type for event handlers
T = TypeVar("T", bound="DomainEvent")
EventHandler = Callable[[T], Awaitable[None]]


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events.

    Domain events are immutable records of something that happened
    in the domain. They carry information about the event but are
    not commands or queries.
    """

    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        """Validate the event after initialization."""
        pass


# === Music Domain Events ===


@dataclass(frozen=True)
class TrackAddedToQueue(DomainEvent):
    """Event raised when a track is added to the queue."""

    guild_id: int = 0
    track_id: str = ""
    track_title: str = ""
    requested_by_id: int = 0
    queue_position: int = 0


@dataclass(frozen=True)
class TrackStartedPlaying(DomainEvent):
    """Event raised when a track starts playing."""

    guild_id: int = 0
    track_id: str = ""
    track_title: str = ""
    track_url: str = ""
    duration_seconds: int | None = None


@dataclass(frozen=True)
class TrackFinishedPlaying(DomainEvent):
    """Event raised when a track finishes playing."""

    guild_id: int = 0
    track_id: str = ""
    track_title: str = ""
    was_skipped: bool = False


@dataclass(frozen=True)
class TrackSkipped(DomainEvent):
    """Event raised when a track is skipped."""

    guild_id: int = 0
    track_id: str = ""
    track_title: str = ""
    skipped_by_id: int = 0
    via_vote: bool = False


@dataclass(frozen=True)
class QueueCleared(DomainEvent):
    """Event raised when the queue is cleared."""

    guild_id: int = 0
    cleared_by_id: int = 0
    track_count: int = 0


@dataclass(frozen=True)
class PlaybackStopped(DomainEvent):
    """Event raised when playback is stopped."""

    guild_id: int = 0
    stopped_by_id: int = 0


@dataclass(frozen=True)
class PlaybackPaused(DomainEvent):
    """Event raised when playback is paused."""

    guild_id: int = 0
    paused_by_id: int = 0


@dataclass(frozen=True)
class PlaybackResumed(DomainEvent):
    """Event raised when playback is resumed."""

    guild_id: int = 0
    resumed_by_id: int = 0


@dataclass(frozen=True)
class QueueExhausted(DomainEvent):
    """Event raised when the queue is empty after a track finishes."""

    guild_id: int = 0
    last_track_id: str = ""
    last_track_title: str = ""


# === Voice Events ===


@dataclass(frozen=True)
class BotJoinedVoiceChannel(DomainEvent):
    """Event raised when the bot joins a voice channel."""

    guild_id: int = 0
    channel_id: int = 0
    channel_name: str = ""


@dataclass(frozen=True)
class BotLeftVoiceChannel(DomainEvent):
    """Event raised when the bot leaves a voice channel."""

    guild_id: int = 0
    channel_id: int = 0
    reason: str = ""  # e.g., "manual", "auto_disconnect", "kicked"


@dataclass(frozen=True)
class VoiceChannelEmpty(DomainEvent):
    """Event raised when the bot's voice channel becomes empty."""

    guild_id: int = 0
    channel_id: int = 0


@dataclass(frozen=True)
class VoiceMemberJoinedVoiceChannel(DomainEvent):
    """Event raised when a non-bot member joins a voice channel."""

    guild_id: int = 0
    channel_id: int = 0
    user_id: int = 0


@dataclass(frozen=True)
class VoiceMemberLeftVoiceChannel(DomainEvent):
    """Event raised when a non-bot member leaves a voice channel."""

    guild_id: int = 0
    channel_id: int = 0
    user_id: int = 0


# === Vote Events ===


@dataclass(frozen=True)
class VoteSkipStarted(DomainEvent):
    """Event raised when a vote skip is initiated."""

    guild_id: int = 0
    track_id: str = ""
    initiated_by_id: int = 0
    votes_needed: int = 0


@dataclass(frozen=True)
class VoteSkipCast(DomainEvent):
    """Event raised when a vote is cast in a skip vote."""

    guild_id: int = 0
    voter_id: int = 0
    current_votes: int = 0
    votes_needed: int = 0


@dataclass(frozen=True)
class VoteSkipPassed(DomainEvent):
    """Event raised when a vote skip passes."""

    guild_id: int = 0
    track_id: str = ""
    total_votes: int = 0


@dataclass(frozen=True)
class VoteSkipFailed(DomainEvent):
    """Event raised when a vote skip fails (expires)."""

    guild_id: int = 0
    track_id: str = ""
    total_votes: int = 0
    votes_needed: int = 0


# === Session Events ===


@dataclass(frozen=True)
class SessionCreated(DomainEvent):
    """Event raised when a new guild session is created."""

    guild_id: int = 0


@dataclass(frozen=True)
class SessionDestroyed(DomainEvent):
    """Event raised when a guild session is destroyed."""

    guild_id: int = 0
    reason: str = ""  # e.g., "cleanup", "manual", "guild_leave"


# === Event Bus ===


class EventBus:
    """In-memory event bus for domain events.

    The event bus allows components to publish and subscribe to domain events
    without tight coupling between publishers and subscribers.

    Usage:
        bus = EventBus()

        # Subscribe to events
        async def on_track_started(event: TrackStartedPlaying):
            print(f"Now playing: {event.track_title}")

        bus.subscribe(TrackStartedPlaying, on_track_started)

        # Publish events
        await bus.publish(TrackStartedPlaying(
            guild_id=123,
            track_id="abc",
            track_title="My Song",
            track_url="https://...",
        ))
    """

    def __init__(self) -> None:
        """Initialize the event bus."""
        self._handlers: dict[type[DomainEvent], list[EventHandler[Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def subscribe(
        self,
        event_type: type[T],
        handler: EventHandler[T],
    ) -> None:
        """Subscribe a handler to an event type.

        Args:
            event_type: The type of event to listen for.
            handler: The async function to call when the event is published.
        """
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed handler to: %s", event_type.__name__)

    def unsubscribe(
        self,
        event_type: type[T],
        handler: EventHandler[T],
    ) -> None:
        """Unsubscribe a handler from an event type.

        Args:
            event_type: The type of event.
            handler: The handler to remove.
        """
        handlers = self._handlers[event_type]
        if handler in handlers:
            handlers.remove(handler)
            logger.debug("Unsubscribed handler from %s", event_type.__name__)

    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to all subscribers.

        Handlers are called concurrently. Exceptions in handlers are logged
        but do not prevent other handlers from running.

        Args:
            event: The domain event to publish.
        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            logger.debug("No handlers for %s", event_type.__name__)
            return

        logger.debug("Publishing %s to %d handlers", event_type.__name__, len(handlers))

        # Run all handlers concurrently using TaskGroup for better error handling
        async def safe_call(handler: EventHandler[Any]) -> None:
            try:
                await handler(event)
            except Exception as e:
                logger.exception("Error in handler for %s: %s", event_type.__name__, e)

        try:
            async with asyncio.TaskGroup() as tg:
                for handler in handlers:
                    tg.create_task(safe_call(handler))
        except* Exception:
            # Errors are already logged in safe_call, no need to re-log
            pass

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
        logger.debug("Cleared all event handlers")


# Global event bus instance
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance.

    Returns:
        The global EventBus instance.
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> None:
    """Reset the global event bus (useful for testing)."""
    global _event_bus
    if _event_bus is not None:
        _event_bus.clear()
    _event_bus = None
