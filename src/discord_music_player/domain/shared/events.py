"""Domain event bus for publishing and subscribing to events."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.shared.datetime_utils import utcnow
from discord_music_player.domain.shared.types import (
    DiscordSnowflake,
    NonEmptyStr,
    NonNegativeInt,
    UtcDatetimeField,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="DomainEvent")
EventHandler = Callable[[T], Awaitable[None]]


class DomainEvent(BaseModel):
    """Base class for all domain events."""

    model_config = ConfigDict(frozen=True)

    event_id: NonEmptyStr = Field(default_factory=lambda: str(uuid4()))
    occurred_at: UtcDatetimeField = Field(default_factory=utcnow)


# === Music Domain Events ===


class TrackAddedToQueue(DomainEvent):
    guild_id: DiscordSnowflake = 0
    track_id: TrackId | None = None
    track_title: str = ""
    requested_by_id: DiscordSnowflake = 0
    queue_position: NonNegativeInt = 0


class TrackStartedPlaying(DomainEvent):
    guild_id: DiscordSnowflake = 0
    track_id: TrackId | None = None
    track_title: str = ""
    track_url: str = ""
    duration_seconds: NonNegativeInt | None = None


class TrackFinishedPlaying(DomainEvent):
    guild_id: DiscordSnowflake = 0
    track_id: TrackId | None = None
    track_title: str = ""
    was_skipped: bool = False


class TrackSkipped(DomainEvent):
    guild_id: DiscordSnowflake = 0
    track_id: TrackId | None = None
    track_title: str = ""
    skipped_by_id: DiscordSnowflake = 0
    via_vote: bool = False


class QueueCleared(DomainEvent):
    guild_id: DiscordSnowflake = 0
    cleared_by_id: DiscordSnowflake = 0
    track_count: NonNegativeInt = 0


class PlaybackStopped(DomainEvent):
    guild_id: DiscordSnowflake = 0
    stopped_by_id: DiscordSnowflake = 0


class PlaybackPaused(DomainEvent):
    guild_id: DiscordSnowflake = 0
    paused_by_id: DiscordSnowflake = 0


class PlaybackResumed(DomainEvent):
    guild_id: DiscordSnowflake = 0
    resumed_by_id: DiscordSnowflake = 0


class QueueExhausted(DomainEvent):
    guild_id: DiscordSnowflake = 0
    last_track_id: TrackId | None = None
    last_track_title: str = ""


# === Voice Events ===


class BotJoinedVoiceChannel(DomainEvent):
    guild_id: DiscordSnowflake = 0
    channel_id: DiscordSnowflake = 0
    channel_name: str = ""


class BotLeftVoiceChannel(DomainEvent):
    guild_id: DiscordSnowflake = 0
    channel_id: DiscordSnowflake = 0
    reason: str = ""


class VoiceChannelEmpty(DomainEvent):
    guild_id: DiscordSnowflake = 0
    channel_id: DiscordSnowflake = 0


class VoiceMemberJoinedVoiceChannel(DomainEvent):
    guild_id: DiscordSnowflake = 0
    channel_id: DiscordSnowflake = 0
    user_id: DiscordSnowflake = 0


class VoiceMemberLeftVoiceChannel(DomainEvent):
    guild_id: DiscordSnowflake = 0
    channel_id: DiscordSnowflake = 0
    user_id: DiscordSnowflake = 0


# === Vote Events ===


class VoteSkipStarted(DomainEvent):
    guild_id: DiscordSnowflake = 0
    track_id: TrackId | None = None
    initiated_by_id: DiscordSnowflake = 0
    votes_needed: NonNegativeInt = 0


class VoteSkipCast(DomainEvent):
    guild_id: DiscordSnowflake = 0
    voter_id: DiscordSnowflake = 0
    current_votes: NonNegativeInt = 0
    votes_needed: NonNegativeInt = 0


class VoteSkipPassed(DomainEvent):
    guild_id: DiscordSnowflake = 0
    track_id: TrackId | None = None
    total_votes: NonNegativeInt = 0


class VoteSkipFailed(DomainEvent):
    guild_id: DiscordSnowflake = 0
    track_id: TrackId | None = None
    total_votes: NonNegativeInt = 0
    votes_needed: NonNegativeInt = 0


# === Session Events ===


class SessionCreated(DomainEvent):
    guild_id: DiscordSnowflake = 0


class SessionDestroyed(DomainEvent):
    guild_id: DiscordSnowflake = 0
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
