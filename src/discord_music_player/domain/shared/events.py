"""Domain event bus for publishing and subscribing to events."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar
from uuid import uuid4

from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.shared.datetime_utils import utcnow

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="DomainEvent")
EventHandler = Callable[[T], Awaitable[None]]


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=utcnow)


# === Music Domain Events ===


@dataclass(frozen=True)
class TrackAddedToQueue(DomainEvent):
    guild_id: int = 0
    track_id: TrackId | None = None
    track_title: str = ""
    requested_by_id: int = 0
    queue_position: int = 0


@dataclass(frozen=True)
class TrackStartedPlaying(DomainEvent):
    guild_id: int = 0
    track_id: TrackId | None = None
    track_title: str = ""
    track_url: str = ""
    duration_seconds: int | None = None


@dataclass(frozen=True)
class TrackFinishedPlaying(DomainEvent):
    guild_id: int = 0
    track_id: TrackId | None = None
    track_title: str = ""
    was_skipped: bool = False


@dataclass(frozen=True)
class TrackSkipped(DomainEvent):
    guild_id: int = 0
    track_id: TrackId | None = None
    track_title: str = ""
    skipped_by_id: int = 0
    via_vote: bool = False


@dataclass(frozen=True)
class QueueCleared(DomainEvent):
    guild_id: int = 0
    cleared_by_id: int = 0
    track_count: int = 0


@dataclass(frozen=True)
class PlaybackStopped(DomainEvent):
    guild_id: int = 0
    stopped_by_id: int = 0


@dataclass(frozen=True)
class PlaybackPaused(DomainEvent):
    guild_id: int = 0
    paused_by_id: int = 0


@dataclass(frozen=True)
class PlaybackResumed(DomainEvent):
    guild_id: int = 0
    resumed_by_id: int = 0


@dataclass(frozen=True)
class QueueExhausted(DomainEvent):
    guild_id: int = 0
    last_track_id: TrackId | None = None
    last_track_title: str = ""


# === Voice Events ===


@dataclass(frozen=True)
class BotJoinedVoiceChannel(DomainEvent):
    guild_id: int = 0
    channel_id: int = 0
    channel_name: str = ""


@dataclass(frozen=True)
class BotLeftVoiceChannel(DomainEvent):
    guild_id: int = 0
    channel_id: int = 0
    reason: str = ""


@dataclass(frozen=True)
class VoiceChannelEmpty(DomainEvent):
    guild_id: int = 0
    channel_id: int = 0


@dataclass(frozen=True)
class VoiceMemberJoinedVoiceChannel(DomainEvent):
    guild_id: int = 0
    channel_id: int = 0
    user_id: int = 0


@dataclass(frozen=True)
class VoiceMemberLeftVoiceChannel(DomainEvent):
    guild_id: int = 0
    channel_id: int = 0
    user_id: int = 0


# === Vote Events ===


@dataclass(frozen=True)
class VoteSkipStarted(DomainEvent):
    guild_id: int = 0
    track_id: TrackId | None = None
    initiated_by_id: int = 0
    votes_needed: int = 0


@dataclass(frozen=True)
class VoteSkipCast(DomainEvent):
    guild_id: int = 0
    voter_id: int = 0
    current_votes: int = 0
    votes_needed: int = 0


@dataclass(frozen=True)
class VoteSkipPassed(DomainEvent):
    guild_id: int = 0
    track_id: TrackId | None = None
    total_votes: int = 0


@dataclass(frozen=True)
class VoteSkipFailed(DomainEvent):
    guild_id: int = 0
    track_id: TrackId | None = None
    total_votes: int = 0
    votes_needed: int = 0


# === Session Events ===


@dataclass(frozen=True)
class SessionCreated(DomainEvent):
    guild_id: int = 0


@dataclass(frozen=True)
class SessionDestroyed(DomainEvent):
    guild_id: int = 0
    reason: str = ""


# === Event Bus ===


class EventBus:
    """In-memory pub/sub event bus for domain events.

    Handlers are called concurrently. Exceptions in handlers are logged
    but do not prevent other handlers from running.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler[Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: type[T], handler: EventHandler[T]) -> None:
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed handler to: %s", event_type.__name__)

    def unsubscribe(self, event_type: type[T], handler: EventHandler[T]) -> None:
        handlers = self._handlers[event_type]
        if handler in handlers:
            handlers.remove(handler)
            logger.debug("Unsubscribed handler from %s", event_type.__name__)

    async def publish(self, event: DomainEvent) -> None:
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            logger.debug("No handlers for %s", event_type.__name__)
            return

        logger.debug("Publishing %s to %d handlers", event_type.__name__, len(handlers))

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
            pass

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
        logger.debug("Cleared all event handlers")


_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus singleton."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> None:
    """Reset the global event bus (for testing)."""
    global _event_bus
    if _event_bus is not None:
        _event_bus.clear()
    _event_bus = None
