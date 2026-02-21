"""Queue Application Service - manages queue operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from ...domain.music.entities import Track
from ...domain.shared.types import DiscordSnowflake, NonEmptyStr, NonNegativeInt, QueuePositionInt
from ...domain.music.value_objects import LoopMode
from ...domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository
    from ...domain.music.services import QueueDomainService

logger = logging.getLogger(__name__)


class EnqueueResult(BaseModel):
    success: bool
    track: Track | None = None
    position: NonNegativeInt = 0
    queue_length: NonNegativeInt = 0
    message: str = ""
    should_start: bool = False


class QueueInfo(BaseModel):

    current_track: Track | None
    upcoming_tracks: list[Track]
    total_length: NonNegativeInt
    total_duration_seconds: NonNegativeInt | None

    @property
    def tracks(self) -> list[Track]:
        return self.upcoming_tracks

    @property
    def total_tracks(self) -> int:
        return self.total_length

    @property
    def total_duration(self) -> int | None:
        return self.total_duration_seconds


class QueueApplicationService:
    """Manages queue operations (add, remove, reorder, shuffle) for guilds."""

    def __init__(
        self,
        *,
        session_repository: SessionRepository,
        queue_domain_service: QueueDomainService,
    ) -> None:
        self._session_repo = session_repository
        self._queue_service = queue_domain_service

    async def enqueue(
        self,
        guild_id: DiscordSnowflake,
        track: Track,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
    ) -> EnqueueResult:
        session = await self._session_repo.get_or_create(guild_id)

        if session._is_duplicate(track):
            return EnqueueResult(
                success=False,
                message=f'"{track.title}" is already in the queue or currently playing',
            )

        if not session.can_add_to_queue:
            return EnqueueResult(
                success=False,
                message=f"Queue is full (max {session.MAX_QUEUE_SIZE} tracks)",
            )

        was_idle = session.current_track is None

        track_with_requester = track.with_requester(
            user_id=user_id,
            user_name=user_name,
            requested_at=datetime.now(UTC),
        )

        position = session.enqueue(track_with_requester)
        await self._session_repo.save(session)

        logger.info(LogTemplates.QUEUE_ENQUEUED, track.title, position.value, guild_id)

        if was_idle:
            message = f"Now playing: {track.title}"
        else:
            message = f"Added to queue at position {position.value + 1}"

        return EnqueueResult(
            success=True,
            track=track_with_requester,
            position=position.value,
            queue_length=session.queue_length,
            message=message,
            should_start=was_idle,
        )

    async def enqueue_next(
        self,
        guild_id: DiscordSnowflake,
        track: Track,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
    ) -> EnqueueResult:
        """Add a track to the front of the queue."""
        session = await self._session_repo.get_or_create(guild_id)

        if session._is_duplicate(track):
            return EnqueueResult(
                success=False,
                message=f'"{track.title}" is already in the queue or currently playing',
            )

        if not session.can_add_to_queue:
            return EnqueueResult(
                success=False,
                message=f"Queue is full (max {session.MAX_QUEUE_SIZE} tracks)",
            )

        track_with_requester = track.with_requester(
            user_id=user_id,
            user_name=user_name,
            requested_at=datetime.now(UTC),
        )

        position = session.enqueue_next(track_with_requester)
        await self._session_repo.save(session)

        logger.info(LogTemplates.QUEUE_ENQUEUED_NEXT, track.title, guild_id)

        return EnqueueResult(
            success=True,
            track=track_with_requester,
            position=position.value,
            queue_length=session.queue_length,
            message="Added to play next",
        )

    async def remove(self, guild_id: DiscordSnowflake, position: QueuePositionInt) -> Track | None:
        session = await self._session_repo.get(guild_id)
        if session is None:
            return None

        track = session.remove_at(position)
        if track:
            await self._session_repo.save(session)
            logger.info(LogTemplates.QUEUE_REMOVED, track.title, guild_id)

        return track

    async def clear(self, guild_id: DiscordSnowflake) -> int:
        session = await self._session_repo.get(guild_id)
        if session is None:
            return 0

        count = session.clear_queue()
        await self._session_repo.save(session)
        logger.info(LogTemplates.QUEUE_CLEARED, count, guild_id)
        return count

    async def clear_recommendations(self, guild_id: DiscordSnowflake) -> int:
        """Clear only AI-recommended tracks from the queue."""
        session = await self._session_repo.get(guild_id)
        if session is None:
            return 0

        count = session.clear_recommendations()
        await self._session_repo.save(session)
        logger.info("Cleared %d AI recommendations from queue in guild %s", count, guild_id)
        return count

    async def shuffle(self, guild_id: DiscordSnowflake) -> bool:
        session = await self._session_repo.get(guild_id)
        if session is None or not session.queue:
            return False

        session.shuffle()
        await self._session_repo.save(session)
        logger.info(LogTemplates.QUEUE_SHUFFLED, guild_id)
        return True

    async def move(self, guild_id: DiscordSnowflake, from_pos: QueuePositionInt, to_pos: QueuePositionInt) -> bool:
        session = await self._session_repo.get(guild_id)
        if session is None:
            return False

        success = session.move_track(from_pos, to_pos)
        if success:
            await self._session_repo.save(session)
            logger.info(LogTemplates.QUEUE_MOVED, from_pos, to_pos, guild_id)

        return success

    async def get_queue(self, guild_id: DiscordSnowflake) -> QueueInfo:
        session = await self._session_repo.get(guild_id)
        if session is None:
            return QueueInfo(
                current_track=None,
                upcoming_tracks=[],
                total_length=0,
                total_duration_seconds=None,
            )

        total_duration = 0
        has_all_durations = True

        if session.current_track and session.current_track.duration_seconds:
            total_duration += session.current_track.duration_seconds
        elif session.current_track:
            has_all_durations = False

        for track in session.queue:
            if track.duration_seconds:
                total_duration += track.duration_seconds
            else:
                has_all_durations = False

        return QueueInfo(
            current_track=session.current_track,
            upcoming_tracks=list(session.queue),
            total_length=session.queue_length + (1 if session.current_track else 0),
            total_duration_seconds=total_duration if has_all_durations else None,
        )

    async def toggle_loop(self, guild_id: DiscordSnowflake) -> LoopMode:
        session = await self._session_repo.get_or_create(guild_id)
        new_mode = session.toggle_loop()
        await self._session_repo.save(session)
        logger.info(LogTemplates.LOOP_MODE_CHANGED, new_mode.value, guild_id)
        return new_mode
