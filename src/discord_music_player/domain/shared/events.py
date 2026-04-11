"""Domain event bus for publishing and subscribing to events."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ...utils.logging import get_logger
from ..music.wrappers import TrackId
from .datetime_utils import utcnow
from .types import (
    ChannelIdField,
    DiscordSnowflake,
    NonEmptyStr,
    NonNegativeInt,
    UserIdField,
)

logger = get_logger(__name__)

T = TypeVar("T", bound="DomainEvent")
EventHandler = Callable[[T], Awaitable[None]]


class DomainEvent(BaseModel):
    """Base class for all domain events."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = Field(default_factory=utcnow)


# === Music Domain Events ===


class TrackStartedPlaying(DomainEvent):
    guild_id: DiscordSnowflake
    track_id: TrackId
    track_title: NonEmptyStr | None = None
    track_url: NonEmptyStr | None = None
    duration_seconds: NonNegativeInt | None = None


class TrackFinishedPlaying(DomainEvent):
    guild_id: DiscordSnowflake
    track_id: TrackId
    track_title: NonEmptyStr | None = None
    was_skipped: bool = False


class QueueExhausted(DomainEvent):
    guild_id: DiscordSnowflake
    last_track_id: TrackId | None = None
    last_track_title: NonEmptyStr | None = None


# === Radio Events ===


class RadioPoolExhausted(DomainEvent):
    """All recommendations in the current radio batch have been consumed."""

    guild_id: DiscordSnowflake
    channel_id: ChannelIdField | None = None
    tracks_generated: NonNegativeInt = 0


# === Voice Events ===


class VoiceMemberJoinedVoiceChannel(DomainEvent):
    guild_id: DiscordSnowflake
    channel_id: ChannelIdField
    user_id: UserIdField


class VoiceMemberLeftVoiceChannel(DomainEvent):
    guild_id: DiscordSnowflake
    channel_id: ChannelIdField
    user_id: UserIdField


# === Event Bus ===


class EventBus:
    """In-memory pub/sub event bus for domain events.

    Handlers are called concurrently. Exceptions in handlers are logged
    but do not prevent other handlers from running.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler[Any]]] = defaultdict(list)

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
        except* Exception as eg:
            logger.error("Unexpected errors in event bus TaskGroup: %s", eg.exceptions)

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
